import type { Polygon } from 'geojson'
import { fetchApi, request } from './api'

export type Narrative = { source: 'template' | 'ai' | 'cached_ai'; text: string }
export const landRoles = { farmer: 'Farmer', buyer: 'Land buyer', analyst: 'Land analyst', planner: 'Local planner' } as const
export const landPurposes = { crops: 'Assess vegetation and crop conditions', site: 'Screen a plot before a site visit',
  water: 'Explore water and drought exposure', change: 'Track land change over time' } as const
export type LandFocus = { role: keyof typeof landRoles; purpose: keyof typeof landPurposes }
export type LandGuidance = { evidence: string; checks: string[]; narrative: Narrative | null;
  ai_status: 'not_requested' | 'unavailable' | 'busy' | 'failed' | 'ready' }
export type TerrainGrid = { cell_m: number; elevations_m: (number | null)[][]; source: string; credit: string }
export type TerrainStorage = (number | null)[][]
export type LandObservation = {
  start: string; end: string
  scenes: { id: string; acquired_at: string }[]
  clear_pct: number; classified_pct: number; land_cover_pct: Record<string, number>
  ndvi: number | null; ndmi: number | null; mapped_water_pct: number | null; soil_moisture_pct: number | null
  image_offset: { east_m: number; north_m: number; matched_blocks: number; from_period: string } | null
  image: string | null
}
export type LandDemo = { id: string; title: string; terrain: 'farmland' | 'dryland' }
export type LandProfile = {
  id: string; title: string; terrain: LandDemo['terrain'] | null; aoi: Polygon; area_km2: number; grid_m: number
  observations: LandObservation[]; scenario_period: string | null; narrative: Narrative | null
}
export type ScenarioInput = {
  days: number; rain_mm_week: number; demand_mm_day: number; storage_capacity_mm: number; initial_storage_pct: number
}
export type Scenario = {
  frames: { day: number; mean_storage_pct: number; low_storage_area_pct: number; mean_overflow_mm: number; image: string;
    terrain_storage_pct: TerrainStorage | null }[]
  inputs: ScenarioInput; modeled_cells: number; baseline: string
  recorded_rain: { start: string; daily_mm: number[]; source: string } | null
}

export type ImageEvidence = Pick<LandObservation, 'start' | 'end' | 'scenes' | 'clear_pct'> & { image: string }
export type HistoryEvidence = { earlier: ImageEvidence; recent: ImageEvidence; grid_m: number }
export type InspectionEvidence = {
  earlier: ImageEvidence[]; recent: ImageEvidence; shared_pct: number; grid_m: number
  min_drop: number; min_cells: number; highlight: string
  patches: { id: number; hectares: number; earlier_greenness: number; recent_greenness: number;
    x_pct: number; y_pct: number; latitude: number; longitude: number }[]
}
export type PlotEvidence = { water_area_pct: number | null; water_coverage_pct: number;
  average_slope_deg: number | null; slope_coverage_pct: number }

function post(signal: AbortSignal, body?: unknown): RequestInit {
  return body === undefined ? { method: 'POST', signal } : {
    method: 'POST', signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  }
}

export function getLandCatalog(signal: AbortSignal) {
  return request<{ demos: LandDemo[]; ai_available: boolean }>('land/catalog', { signal })
}
export function getLandProfile(id: string, signal: AbortSignal) {
  return request<LandProfile>(`land/analyses/${encodeURIComponent(id)}`, { signal, cache: 'no-store' })
}
export function getTerrain(id: string, signal: AbortSignal) {
  return request<TerrainGrid>(`land/analyses/${encodeURIComponent(id)}/terrain`, { signal })
}
export type LandStage = 'sources' | 'pixels' | 'summary'
type LandEvent = { type: 'stage'; data: LandStage } | { type: 'result'; data: LandProfile } | { type: 'error'; data: string }

export async function createLandProfile(aoi: Polygon, end: string, months: number, signal: AbortSignal, progress: (stage: LandStage) => void) {
  const response = await fetchApi('land/analyses/stream', post(signal, { aoi, end, months }))
  if (!response.body) throw new Error('The land analysis stream was unavailable.')
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffered = ''
  try {
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffered += value
      const lines = buffered.split('\n')
      buffered = lines.pop() ?? ''
      for (const line of lines) {
        if (!line) continue
        const event = JSON.parse(line) as LandEvent
        if (event.type === 'stage') progress(event.data)
        if (event.type === 'error') throw new Error(event.data)
        if (event.type === 'result') return event.data
      }
    }
    throw new Error('The connection ended before the land analysis returned a result.')
  } finally {
    await reader.cancel().catch(() => undefined)
    reader.releaseLock()
  }
}
export function generateLandNarrative(id: string, signal: AbortSignal) {
  return request<Narrative>(`land/analyses/${encodeURIComponent(id)}/explain`, post(signal))
}
export function getLandGuidance(id: string, focus: LandFocus, useAi: boolean, signal: AbortSignal) {
  return request<LandGuidance>(`land/analyses/${encodeURIComponent(id)}/guidance`, post(signal, { ...focus, use_ai: useAi }))
}
export function getInspection(id: string, signal: AbortSignal) {
  return request<InspectionEvidence>(`land/analyses/${encodeURIComponent(id)}/inspection`, { signal })
}
export function getHistory(id: string, signal: AbortSignal) {
  return request<HistoryEvidence>(`land/analyses/${encodeURIComponent(id)}/history`, { signal })
}
export function getPlotEvidence(id: string, signal: AbortSignal) {
  return request<PlotEvidence>(`land/analyses/${encodeURIComponent(id)}/plot`, { signal })
}
export function simulateLand(id: string, values: ScenarioInput, signal: AbortSignal, monsoonYear?: number) {
  const mode = monsoonYear === undefined ? 'scenario' : `monsoon/${monsoonYear}`
  return request<Scenario>(`land/analyses/${encodeURIComponent(id)}/${mode}`, post(signal, values))
}
