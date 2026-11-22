import type { Polygon } from 'geojson'

type Health = {
  status: 'ok'
  max_aoi_km2: number
  earth_engine: 'not_configured' | 'unverified'
  analysis_available: boolean
}

export type ValidatedArea = {
  area_km2: number
  max_area_km2: number
}

const apiBase = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

export function apiUrl(path: string) {
  return `${apiBase}/api/${path}`
}

export async function fetchApi(path: string, options: RequestInit): Promise<Response> {
  const response = await fetch(apiUrl(path), options)
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    if (typeof body?.detail === 'string') throw new Error(body.detail)
    if (response.status === 422) throw new Error('Check the study boundary and date settings, then try again.')
    throw new Error('The local API is unavailable. Check that the backend is running.')
  }
  return response
}

export async function request<T>(path: string, options: RequestInit): Promise<T> {
  return (await fetchApi(path, options)).json() as Promise<T>
}

export function getHealth(signal: AbortSignal) {
  return request<Health>('health', { signal })
}

export function validateArea(geometry: Polygon, signal: AbortSignal) {
  return request<ValidatedArea>('aois/validate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(geometry),
    signal,
  })
}

export type Window = { kind: 'preset'; days: 7 | 30 | 90 }
  | { kind: 'event'; date: string }
  | { kind: 'range'; start: string; event: string; end: string }

export type AnalysisRequest = { source: 'synthetic' } | { source: 'earth_engine'; aoi: Polygon; window: Window }
export type AnalysisSelection = AnalysisRequest | { source: 'cached'; slug: string }
export type DemoEvent = { slug: string; title: string; source: 'synthetic' | 'cached' }
export type Layer = 'before' | 'after' | 'change'
export type Language = 'en' | 'hi'
type Source = AnalysisRequest['source']
type Geometry = { orbit_pass: string; relative_orbit: number; mode: string; polarizations: string[] }
type Observation = { id: string; acquired_at: string; platform: string }

export type Rejection = {
  geometry: Geometry; platform: string | null; footprint_coverage: number | null
  reason: 'missing_before' | 'missing_after' | 'no_shared_coverage' | 'lower_rank'
}

export type Result = {
  id: string; source: Source; title: string; aoi: Polygon; aoi_area_km2: number
  periods: { start: string; event: string; end_exclusive: string }
  geometry: Geometry; pre: Observation[]; post: Observation[]; footprint_coverage_pct: number
  stats: {
    sampled_aoi_km2: number; flood_ha: number; flood_km2: number; flood_pct_of_aoi: number
    preexisting_water_ha: number; valid_coverage_pct: number; masked_terrain_pct: number
  }
  masks_excluded_ha: Record<string, number>
  parameters: {
    scale_m: number; water_db: number; change_db: number; speckle_radius_m: number
    permanent_water_pct: number; max_slope_deg: number; max_hand_m: number; min_cluster_pixels: number
  }
  classification: 'possible_flooding' | 'no_change_detected' | 'insufficient_data'
  quality: { overall: 'High' | 'Medium' | 'Low'; factors: { name: string; observed: string; grade: 'Good' | 'Fair' | 'Poor' }[] }
  warnings: string[]; attributions: string[]; layers: Record<Layer, string>
  bounds: [[number, number], [number, number]]; method_version: string
  cached_event: { slug: string; reference_url: string } | null
}

export type Job = {
  id: string; source: Source; status: 'queued' | 'running' | 'done' | 'failed' | 'no_comparable_pair'
  stage: 'finding_scenes' | 'computing' | 'rendering' | null
  message: string | null; code: string | null; result: Result | null; rejections: Rejection[]
}

export type Explanation = { headline: string; summary: string; limitations: string[]; verification: string; language: Language }

export function submitAnalysis(analysis: AnalysisRequest, signal: AbortSignal) {
  return request<Job>('analyses', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(analysis), signal,
  })
}

export function getDemoEvents(signal: AbortSignal) {
  return request<DemoEvent[]>('demo/events', { signal })
}

export function getCachedEvent(slug: string, signal: AbortSignal) {
  return request<Job>(`demo/events/${encodeURIComponent(slug)}`, { signal })
}

export function getJob(id: string, signal: AbortSignal) {
  return request<Job>(`analyses/${id}`, { signal, cache: 'no-store' })
}

export function getExplanation(id: string, lang: Language, signal: AbortSignal) {
  return request<Explanation>(`analyses/${id}/explain?lang=${lang}`, { method: 'POST', signal })
}
