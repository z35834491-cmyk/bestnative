import type { TopoEdge, TopoNode } from '@/lib/types'

/** 分层布局：服务按调用链从左到右，中间件在底部一行 */
export function layoutNodes(nodes: TopoNode[], edges: TopoEdge[], entryService?: string): TopoNode[] {
  if (!nodes.length) return []

  const NW = 160, NH = 88, HX = 100, VY = 56
  const services = nodes.filter(n => n.type === 'service')
  const middlewares = nodes.filter(n => n.type === 'middleware')

  const resolve = (key: string) => nodes.find(n => n.id === key || n.name === key)

  const adj = new Map<string, string[]>()
  const inDeg = new Map<string, number>()
  for (const s of services) {
    adj.set(s.id, [])
    inDeg.set(s.id, 0)
  }
  for (const e of edges) {
    const fromNode = resolve(e.from || e.source || '')
    const toNode = resolve(e.to || e.target || '')
    if (!fromNode || !toNode) continue
    if (fromNode.type === 'service' && toNode.type === 'service') {
      adj.get(fromNode.id)!.push(toNode.id)
      inDeg.set(toNode.id, (inDeg.get(toNode.id) || 0) + 1)
    }
  }

  let roots = services.filter(s => (inDeg.get(s.id) || 0) === 0).map(s => s.id)
  if (entryService) {
    const entry = services.find(s => s.name === entryService)
    if (entry) roots = [entry.id]
  }
  if (!roots.length && services.length) {
    roots = [services.sort((a, b) => (b.traceCount || 0) - (a.traceCount || 0))[0].id]
  }

  const layer = new Map<string, number>()
  const queue = [...roots]
  roots.forEach(r => layer.set(r, 0))
  while (queue.length) {
    const cur = queue.shift()!
    const d = layer.get(cur) || 0
    for (const nxt of adj.get(cur) || []) {
      if (!layer.has(nxt) || layer.get(nxt)! > d + 1) {
        layer.set(nxt, d + 1)
        queue.push(nxt)
      }
    }
  }
  for (const s of services) {
    if (!layer.has(s.id)) layer.set(s.id, 0)
  }

  const byLayer = new Map<number, TopoNode[]>()
  for (const s of services) {
    const l = layer.get(s.id) || 0
    if (!byLayer.has(l)) byLayer.set(l, [])
    byLayer.get(l)!.push(s)
  }
  byLayer.forEach(list => list.sort((a, b) => (b.traceCount || 0) - (a.traceCount || 0)))

  const positioned = new Map<string, TopoNode>()
  const maxLayer = Math.max(...byLayer.keys(), 0)
  let globalMaxY = 0

  for (let l = 0; l <= maxLayer; l++) {
    const list = byLayer.get(l) || []
    const colH = list.length * NH + Math.max(0, list.length - 1) * VY
    const startY = Math.max(48, 240 - colH / 2)
    list.forEach((n, i) => {
      const y = startY + i * (NH + VY)
      positioned.set(n.id, { ...n, x: 48 + l * (NW + HX), y })
      globalMaxY = Math.max(globalMaxY, y + NH)
    })
  }

  const midY = globalMaxY + 64
  middlewares.forEach((n, i) => {
    positioned.set(n.id, { ...n, x: 48 + i * (NW + HX), y: midY })
  })

  return nodes.map(n => positioned.get(n.id) || { ...n, x: 48, y: 48 + nodes.indexOf(n) * (NH + VY) })
}

export function graphBounds(nodes: TopoNode[]) {
  const maxX = Math.max(...nodes.map(n => (n.x || 0) + 170), 600) + 40
  const maxY = Math.max(...nodes.map(n => (n.y || 0) + 96), 320) + 40
  return { maxX, maxY }
}
