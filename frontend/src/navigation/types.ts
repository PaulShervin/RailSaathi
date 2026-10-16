// Types for station navigation (backend/app/navigation, merged from Navigation_exp).
// Mirrors backend/app/navigation/models.py; only the fields this app uses are listed.

export type Point = [number, number] // normalized image coordinates (0..1)
export type NavAccessibility = 'verified' | 'not_accessible' | 'unknown'
export type NavVerification = 'verified' | 'simulated' | 'pending'

export interface NavStationSummary {
  station_id: string
  station_name: string
  node_count: number
  edge_count: number
  data_status: string
  city: string | null
}

export interface NavNode {
  id: string
  name: string
  type: string
  position: Point
  verification: NavVerification
  accessible: NavAccessibility
  status: 'open' | 'closed' | 'unknown'
}

export interface NavEdge {
  id: string
  from: string
  to: string
  path_type: string
  status: 'open' | 'closed' | 'unknown'
  verification: NavVerification
  accessible: NavAccessibility
  geometry: Point[]
  notes?: string | null
}

export interface NavStation {
  station_id: string
  station_name: string
  map: { image: string; width: number; height: number }
  nodes: NavNode[]
  edges: NavEdge[]
}

export interface NavStationResponse {
  station: NavStation
  metadata: { data_status?: string; notes?: string[]; city?: string | null } | null
}

export interface RoutePreferences {
  avoid_stairs: boolean
  wheelchair: boolean
  require_verified_accessibility: boolean
}

export interface RouteInstruction {
  step: number
  text: string
  node_id: string
  edge_id?: string | null
  distance_m?: number | null
  distance_is_estimate: boolean
}

export interface RouteSegment {
  edge_id: string
  from_node: string
  to_node: string
  geometry: Point[]
  verification: NavVerification
  accessible: NavAccessibility
}

export interface AlongTheWayItem {
  node_id: string
  name: string
  type: string
  on_route: boolean
  distance_from_route_m: number | null
  progress: number
}

export interface NavRoute {
  status: 'ok' | 'no_route'
  station_id: string
  source: string
  destination: string
  node_ids: string[]
  edge_ids: string[]
  geometry: Point[]
  segments: RouteSegment[]
  distance_m: number | null
  estimated_distance_m: number | null
  distance_basis: 'measured' | 'estimated_from_map_scale' | 'unavailable'
  estimated_duration_s: number | null
  duration_assumption: string | null
  accessibility_confidence: 'verified' | 'unverified' | 'not_applicable'
  warnings: string[]
  instructions: RouteInstruction[]
  reason: string | null
  explanation: string | null
  blocking_edge_ids: string[]
  previous_route_blocked: boolean
  previous_route_blocked_edge_ids: string[]
  simulated_disruptions_applied: string[]
  along_the_way: AlongTheWayItem[]
}

export interface NavDisruption {
  id: string
  target_type: 'edge' | 'node'
  target_id: string
  kind: string
  reason: string
  simulated: true
}

export interface Helpline {
  number: string | null
  name?: string
  label?: string
  confidence?: string
  url?: string
}

export interface StationInfo {
  checked_on?: string
  disclaimer?: string
  helplines: Helpline[]
}
