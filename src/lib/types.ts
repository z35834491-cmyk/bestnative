// API response types — mirror backend schemas

export type HealthStatus = 'healthy' | 'degraded' | 'critical' | 'unknown'

export interface KpiData {
  totalServices: number
  healthyRate: number
  activeIncidents: number
  todayAlerts: number
}

// ---- Topology (from /api/topology/*) ----

export interface ClusterInfo {
  id: string
  name: string
  provider: string
  health: HealthStatus
  nodeCount: number
}

export interface TopoNode {
  id: string
  name: string
  type: 'service' | 'middleware' | 'ingress'
  namespace: string
  health: HealthStatus
  replicas?: number
  readyReplicas?: number
  version?: string
  component?: 'mysql' | 'redis' | 'rabbitmq' | string
  traceCount?: number
  errorCount?: number
  lastSeen?: string
  // layout: auto-calculated by frontend
  x?: number
  y?: number
}

export interface TopoEdge {
  from?: string
  to?: string
  source?: string
  target?: string
  latencyMs?: number
  avgLatencyMs?: number
  p95LatencyMs?: number
  latencySamples?: number
  health?: HealthStatus
  detectedBy?: string
  traceCount?: number
  errorCount?: number
  lastTraceId?: string
  lastSeen?: string
}

export interface TopologyGraph {
  nodes: TopoNode[]
  edges?: TopoEdge[]
}

export interface TraceSummary {
  traceId: string
  services: string[]
  components?: string[]
  eventCount: number
  hasError: boolean
  firstSeen?: string
  lastSeen?: string
  maxDurationMs?: number | null
}

export interface TraceGraph extends TopologyGraph {
  traces: TraceSummary[]
  source: string
  hours: number
  service: string
}

export interface TraceEvent {
  timestamp: string
  traceId: string
  spanId: string
  serviceName: string
  podName: string
  podNodeName: string
  thread: string
  logLevel: string
  javaModule: string
  lineNum: string
  logMessage: string
  durationMs?: number | null
  component?: 'mysql' | 'redis' | 'rabbitmq' | string | null
}

export interface TraceTimeline {
  traceId: string
  services: string[]
  events: TraceEvent[]
  eventCount: number
  hasError: boolean
}

// ---- Incidents ----

export type IncidentSeverity = 'critical' | 'warning' | 'info'
export type IncidentStatus = 'firing' | 'acknowledged' | 'analyzing' | 'analyzed' | 'resolved'

export interface Incident {
  id: string
  title: string
  severity: IncidentSeverity
  status: IncidentStatus
  source: string
  affectedServices: string[]
  assignee: string
  createdAt: string
  resolvedAt: string | null
}

export interface IncidentEvent {
  type: string
  actor: string
  content: string
  at: string
}

export interface AnalysisReport {
  rootCause: string
  evidence: string[]
  recommendation: string
  confidence: string
  canAutoFix: boolean
  tokens: number
}

export interface IncidentDetail extends Incident {
  timeline: IncidentEvent[]
  reports: AnalysisReport[]
}
