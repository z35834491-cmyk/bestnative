# ============================================================
# app/api/monitor.py — 日志监控 API（合并自 shark-Platform monitor）
# ============================================================

from __future__ import annotations

import datetime
import json
import math
import os
from collections import deque
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.monitor import MonitorTask
from app.schemas.monitor import BatchSearchRequest, MonitorTaskCreate, MonitorTaskUpdate
from app.services.log_monitor.engine import monitor_engine
from app.services.log_monitor.s3_helpers import (
    get_s3_client,
    handle_s3_error,
    index_s3_key,
    iter_s3_lines,
    latest_completed_4h_window_start,
    list_log_files,
    redact_task,
    task_s3_prefixes,
)
from app.services.log_monitor.engine import _make_aware, _now, monitor_engine

router = APIRouter(prefix="/monitor", tags=["monitor"])


async def _get_task(db: AsyncSession, task_id: UUID) -> MonitorTask:
    task = (await db.execute(select(MonitorTask).where(MonitorTask.id == task_id))).scalar_one_or_none()
    if task is None:
        raise HTTPException(404, "Task not found")
    return task


@router.get("/tasks")
async def list_tasks(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(MonitorTask).order_by(MonitorTask.created_at.desc()))).scalars().all()
    return [redact_task(t) for t in rows]


@router.post("/tasks")
async def create_task(body: MonitorTaskCreate, db: AsyncSession = Depends(get_db)):
    task = MonitorTask(**body.model_dump())
    db.add(task)
    await db.flush()
    await db.refresh(task)
    return redact_task(task)


@router.get("/tasks/{task_id}")
async def get_task(task_id: UUID, db: AsyncSession = Depends(get_db)):
    return redact_task(await _get_task(db, task_id))


@router.put("/tasks/{task_id}")
async def update_task(task_id: UUID, body: MonitorTaskUpdate, db: AsyncSession = Depends(get_db)):
    task = await _get_task(db, task_id)
    data = body.model_dump(exclude_unset=True)
    for k in ('s3_access_key', 's3_secret_key', 'k8s_kubeconfig'):
        if k in data and not data[k]:
            data.pop(k, None)
    for k, v in data.items():
        setattr(task, k, v)
    await db.flush()
    await db.refresh(task)
    return redact_task(task)


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: UUID, db: AsyncSession = Depends(get_db)):
    task = await _get_task(db, task_id)
    await db.delete(task)
    return {"msg": "deleted"}


@router.get("/logs")
async def monitor_logs(
    task_id: UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    search: str = "",
    sort_by: str = "mtime",
    order: str = "desc",
    log_type: str = "all",
    realtime: bool = False,
    db: AsyncSession = Depends(get_db),
):
    task = await _get_task(db, task_id)
    return list_log_files(
        task, page=page, page_size=page_size, search=search.lower(),
        sort_by=sort_by, order=order, log_type=log_type.lower(), realtime=realtime,
    )


@router.get("/logs/history")
async def monitor_logs_history(
    task_id: UUID,
    log_type: str = "raw",
    start: str | None = None,
    end: str | None = None,
    keyword: str = "",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    task = await _get_task(db, task_id)
    s3_client = get_s3_client(task)
    if not s3_client:
        return {"items": [], "total": 0}

    lt = log_type if log_type in ('raw', 'error') else 'raw'
    now = _now()
    try:
        start_dt = datetime.datetime.fromisoformat(start) if start else (now - datetime.timedelta(days=7))
    except Exception:
        start_dt = now - datetime.timedelta(days=7)
    try:
        end_dt = datetime.datetime.fromisoformat(end) if end else now
    except Exception:
        end_dt = now
    if start_dt.tzinfo is None:
        start_dt = _make_aware(start_dt)
    if end_dt.tzinfo is None:
        end_dt = _make_aware(end_dt)

    prefix = f"logs/monitor/{task.id}/indexes/{lt}/"
    items = []

    def fetch_items(client):
        fetched = []
        paginator = client.get_paginator('list_objects_v2')
        for p in paginator.paginate(Bucket=task.s3_bucket, Prefix=prefix):
            for obj in p.get('Contents', []) or []:
                key = obj.get('Key') or ''
                if not key.endswith('.json'):
                    continue
                if keyword and keyword.lower() not in key.lower():
                    continue
                try:
                    parts = key.split('/')
                    date_str = parts[-2]
                    range_str = parts[-1].replace('.json', '')
                    start_h = int(range_str[:2])
                    ws_dt = datetime.datetime.fromisoformat(date_str).replace(
                        hour=start_h, minute=0, second=0, microsecond=0
                    )
                    ws_dt = _make_aware(ws_dt)
                    we_dt = ws_dt + datetime.timedelta(hours=4) - datetime.timedelta(seconds=1)
                except Exception:
                    continue
                if we_dt < start_dt or ws_dt > end_dt:
                    continue
                lm = obj.get('LastModified')
                fetched.append({
                    "key": key,
                    "window_start": ws_dt.isoformat(),
                    "window_end": we_dt.isoformat(),
                    "mtime": lm.timestamp() if lm else 0,
                    "size": int(obj.get('Size') or 0),
                })
        return fetched

    try:
        items = fetch_items(s3_client)
    except Exception as e:
        async def _save(t):
            pass
        if handle_s3_error(e, task, lambda t: None):
            s3_client = get_s3_client(task)
            try:
                items = fetch_items(s3_client)
            except Exception as retry_e:
                raise HTTPException(500, f"Retry failed: {retry_e}") from retry_e
        else:
            raise HTTPException(500, str(e)) from e

    items.sort(key=lambda x: x.get('window_start') or '', reverse=True)
    total = len(items)
    start_i = (page - 1) * page_size
    return {"items": items[start_i:start_i + page_size], "total": total, "page": page, "page_size": page_size}


@router.get("/logs/index_detail")
async def monitor_index_detail(task_id: UUID, key: str, db: AsyncSession = Depends(get_db)):
    task = await _get_task(db, task_id)
    s3_client = get_s3_client(task)
    if not s3_client:
        raise HTTPException(400, "S3 not enabled")
    prefix = f"logs/monitor/{task.id}/indexes/"
    if not key.startswith(prefix):
        raise HTTPException(400, "invalid parameters")
    try:
        obj = s3_client.get_object(Bucket=task.s3_bucket, Key=key)
        return json.loads(obj['Body'].read().decode('utf-8', errors='replace'))
    except Exception as e:
        if handle_s3_error(e, task, lambda t: None):
            s3_client = get_s3_client(task)
            try:
                obj = s3_client.get_object(Bucket=task.s3_bucket, Key=key)
                return json.loads(obj['Body'].read().decode('utf-8', errors='replace'))
            except Exception:
                pass
        raise HTTPException(404, "Index not found") from e


def _serve_local_file(fpath: str, keyword: str | None, page: int, page_size: int, reverse: bool) -> dict:
    if keyword:
        results = []
        keywords = keyword.lower().split()
        with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                line_lower = line.lower()
                if all(k in line_lower for k in keywords):
                    results.append(line.rstrip())
                    if len(results) > 2000:
                        results.append("... (Matches truncated, found > 2000 lines) ...")
                        break
        return {"content": "\n".join(results), "is_search_result": True, "total": len(results)}

    file_size = os.path.getsize(fpath)
    if file_size > 50 * 1024 * 1024 and not keyword:
        if reverse and page == 1:
            with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                all_lines = list(deque(f, page_size))
                all_lines.reverse()
                return {
                    "content": "".join(all_lines), "total": page_size + 1,
                    "page": 1, "page_size": page_size,
                    "warning": "File too large, showing last lines only.",
                }

    with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
        all_lines = f.readlines()
    total = len(all_lines)
    if reverse:
        all_lines.reverse()
    p = page if page != -1 else max(1, math.ceil(total / page_size))
    start = (p - 1) * page_size
    return {"content": "".join(all_lines[start:start + page_size]), "total": total, "page": p, "page_size": page_size}


@router.get("/logs/view")
async def monitor_log_view(
    task_id: UUID,
    filename: str,
    keyword: str | None = None,
    page: int = Query(1),
    page_size: int = Query(1000, le=5000),
    reverse: bool = False,
    db: AsyncSession = Depends(get_db),
):
    task = await _get_task(db, task_id)

    if filename.endswith('_s3_recent.log'):
        s3_client = get_s3_client(task)
        if s3_client:
            lt = 'raw'
            ws = latest_completed_4h_window_start(_now())
            payload = None
            try:
                payload = monitor_engine.get_realtime_index_payload(task, lt)
            except Exception:
                pass
            if not payload:
                idx_key = index_s3_key(task, lt, ws)
                try:
                    obj = s3_client.get_object(Bucket=task.s3_bucket, Key=idx_key)
                    payload = json.loads(obj['Body'].read().decode('utf-8', errors='replace'))
                except Exception:
                    pass
            target_keys = []
            if payload and isinstance(payload.get('files'), list):
                for f in payload['files']:
                    key = f.get('name') or ''
                    if '/raw/' in key:
                        try:
                            idx = key.find('/raw/')
                            rest = key[idx + 5:]
                            p = rest.split('/')
                            if len(p) >= 4:
                                virtual_name = f"{p[0]}_{p[1]}_s3_recent.log"
                                if virtual_name == filename:
                                    target_keys.append(key)
                        except Exception:
                            pass
            target_keys.sort()
            if keyword:
                results = []
                keywords = keyword.lower().split()
                for key in target_keys:
                    try:
                        obj = s3_client.get_object(Bucket=task.s3_bucket, Key=key)
                        for line in iter_s3_lines(obj['Body']):
                            ll = line.lower()
                            if all(k in ll for k in keywords):
                                results.append(line.rstrip('\n'))
                                if len(results) > 2000:
                                    break
                    except Exception:
                        pass
                return {"content": "\n".join(results), "is_search_result": True, "total": len(results)}
            full_text = ""
            for key in target_keys:
                try:
                    obj = s3_client.get_object(Bucket=task.s3_bucket, Key=key)
                    full_text += obj['Body'].read().decode('utf-8', errors='replace')
                except Exception:
                    pass
            all_lines = full_text.splitlines(True)
            total = len(all_lines)
            if reverse:
                all_lines.reverse()
            p = page if page != -1 else max(1, math.ceil(total / page_size))
            start = (p - 1) * page_size
            return {"content": "".join(all_lines[start:start + page_size]), "total": total, "page": p, "page_size": page_size}

    log_dir = os.path.join(monitor_engine.LOG_DIR, str(task_id))
    local_path = os.path.join(log_dir, filename)
    if not (os.path.sep in filename or '..' in filename) and os.path.exists(local_path):
        return _serve_local_file(local_path, keyword, page, page_size, reverse)

    s3_client = get_s3_client(task)
    if s3_client and any(filename.startswith(p) for p in task_s3_prefixes(task)):
        try:
            head = s3_client.head_object(Bucket=task.s3_bucket, Key=filename)
            size = int(head.get('ContentLength') or 0)
        except Exception as e:
            if handle_s3_error(e, task, lambda t: None):
                s3_client = get_s3_client(task)
                head = s3_client.head_object(Bucket=task.s3_bucket, Key=filename)
                size = int(head.get('ContentLength') or 0)
            else:
                raise HTTPException(404, "File not found") from e
        if keyword:
            results = []
            keywords = keyword.lower().split()
            obj = s3_client.get_object(Bucket=task.s3_bucket, Key=filename)
            for line in iter_s3_lines(obj['Body']):
                ll = line.lower()
                if all(k in ll for k in keywords):
                    results.append(line.rstrip('\n'))
                    if len(results) > 2000:
                        results.append("... (Matches truncated) ...")
                        break
            return {"content": "\n".join(results), "is_search_result": True, "total": len(results)}
        if size > 50 * 1024 * 1024:
            raise HTTPException(413, "File too large")
        obj = s3_client.get_object(Bucket=task.s3_bucket, Key=filename)
        text = obj['Body'].read().decode('utf-8', errors='replace')
        all_lines = text.splitlines(True)
        total = len(all_lines)
        if reverse:
            all_lines.reverse()
        p = page if page != -1 else max(1, math.ceil(total / page_size))
        start = (p - 1) * page_size
        return {"content": "".join(all_lines[start:start + page_size]), "total": total, "page": p, "page_size": page_size}

    raise HTTPException(404, "File not found")


@router.get("/logs/download")
async def monitor_log_download(task_id: UUID, filename: str, db: AsyncSession = Depends(get_db)):
    task = await _get_task(db, task_id)
    log_dir = os.path.join(monitor_engine.LOG_DIR, str(task_id))
    local_path = os.path.join(log_dir, filename)
    if not (os.path.sep in filename or '..' in filename) and os.path.exists(local_path):
        return FileResponse(local_path, filename=filename, media_type='text/plain')

    s3_client = get_s3_client(task)
    if s3_client and any(filename.startswith(p) for p in task_s3_prefixes(task)):
        obj = s3_client.get_object(Bucket=task.s3_bucket, Key=filename)
        out_name = os.path.basename(filename) or "log.log"
        return StreamingResponse(
            iter_s3_lines(obj['Body']),
            media_type='text/plain; charset=utf-8',
            headers={'Content-Disposition': f'attachment; filename="{out_name}"'},
        )
    raise HTTPException(404, "File not found")


@router.post("/logs/batch_search")
async def monitor_log_batch_search(body: BatchSearchRequest, db: AsyncSession = Depends(get_db)):
    task = await _get_task(db, body.task_id)
    s3_client = get_s3_client(task)
    results = []
    max_total = 2000
    keywords = body.keyword.lower().split()
    log_dir = os.path.join(monitor_engine.LOG_DIR, str(body.task_id))
    prefixes = task_s3_prefixes(task)

    for fname in body.filenames:
        if len(results) >= max_total:
            break
        is_s3 = bool(s3_client and any(str(fname).startswith(p) for p in prefixes))
        if is_s3:
            try:
                obj = s3_client.get_object(Bucket=task.s3_bucket, Key=fname)
                for i, line in enumerate(iter_s3_lines(obj['Body']), 1):
                    line_lower = line.lower()
                    if all(k in line_lower for k in keywords):
                        results.append({"file": fname, "line": i, "content": line.strip()})
                        if len(results) >= max_total:
                            break
            except Exception:
                pass
        else:
            if os.path.sep in fname or '..' in fname:
                continue
            fpath = os.path.join(log_dir, fname)
            if not os.path.exists(fpath):
                continue
            try:
                with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
                    for i, line in enumerate(f, 1):
                        line_lower = line.lower()
                        if all(k in line_lower for k in keywords):
                            results.append({"file": fname, "line": i, "content": line.strip()})
                            if len(results) >= max_total:
                                break
            except Exception:
                pass
    return {"results": results}


@router.get("/status")
async def monitor_status():
    return {"running": monitor_engine.is_running(), "log_dir": monitor_engine.LOG_DIR}
