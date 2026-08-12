#!/bin/sh
set -e

# 复制 kubeconfig 到可写位置并设置 context
if [ -f /tmp/kubeconfig.orig ]; then
    cp /tmp/kubeconfig.orig /tmp/kubeconfig
    CTX="${K8S_CONTEXT:-}"
    if [ -n "$CTX" ]; then
        sed -i "s/^current-context:.*/current-context: $CTX/" /tmp/kubeconfig
    fi
    export KUBECONFIG=/tmp/kubeconfig
fi

python -m app.bootstrap
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
