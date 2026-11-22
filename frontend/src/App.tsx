import { useEffect, useId, useRef, useState } from 'react'
import type { Polygon } from 'geojson'
import { Archive, CalendarDays, CircleHelp, FlaskConical, MapPin, Radar, Scan, Search, Satellite, ShieldCheck, Sprout, X } from 'lucide-react'
import { getDemoEvents, getHealth, validateArea, type DemoEvent, type ValidatedArea, type Window } from './api'
import { initialView, locations, type Location } from './locations'
import { LandWorkspace } from './LandWorkspace'
import { AnalysisProgress } from './AnalysisProgress'
import { FloodSummary, PairingDetails, Results } from './Results'
import { StudyMap } from './StudyMap'
import { useAnalysis } from './useAnalysis'

type ApiStatus = 'checking' | 'online' | 'unavailable'
const windows = [7, 30, 90, 'custom'] as const
const areaNumber = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 3 })
const floodSteps = [
  { label: 'Submit study area', detail: 'The server is receiving the study boundary and observation window.' },
  { label: 'Find comparable scenes', detail: 'Matching before and after observations by orbit and coverage.' },
  { label: 'Measure surface-water change', detail: 'Comparing radar pixels and excluding existing water, steep terrain and small patches.' },
  { label: 'Prepare result maps', detail: 'Rendering before, after and detected-change layers.' },
] as const
const floodStageIndex = { finding_scenes: 1, computing: 2, rendering: 3 }

function LocationSearch({ onSelect }: { onSelect: (location: Location) => void }) {
  const [text, setText] = useState('')
  const [open, setOpen] = useState(false)
  const optionsId = useId()
  const query = text.trim().toLowerCase()
  const matches = locations.filter(({ name, region }) => `${name} ${region}`.toLowerCase().includes(query))

  function select(location: Location) {
    setText(location.name)
    setOpen(false)
    onSelect(location)
  }

  return <div className="location-search" onBlur={(event) => {
    if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false)
  }}>
    <label htmlFor="place-search">Example locations</label>
    <div className="search-frame">
      <Search size={18} aria-hidden="true" />
      <input id="place-search" type="search" value={text} placeholder="Search example locations"
        autoComplete="off" aria-controls={open ? optionsId : undefined}
        onChange={(event) => { setText(event.target.value); setOpen(true) }}
        onFocus={() => setOpen(true)}
        onKeyDown={(event) => {
          if (event.key === 'Escape') setOpen(false)
          if (event.key === 'Enter' && open && query && matches[0]) select(matches[0])
        }} />
    </div>
    {open && <ul className="location-options" id={optionsId} aria-label="Matching locations">
      {matches.length ? matches.map((location) => <li key={location.name}>
        <button type="button" onClick={() => select(location)}>
          <MapPin size={15} /><span>{location.name}<small>{location.region}</small></span>
        </button>
      </li>) : <li className="location-empty">No matching example locations.</li>}
    </ul>}
    <div className="location-shortcuts" aria-label="Quick locations">
      {locations.slice(0, 3).map((location) => <button type="button" key={location.name} onClick={() => select(location)}>{location.name}</button>)}
    </div>
  </div>
}

export function App() {
  const [location, setLocation] = useState<Location>(initialView)
  const [locationRevision, setLocationRevision] = useState(0)
  const [geometry, setGeometry] = useState<Polygon | null>(null)
  const [checkedArea, setCheckedArea] = useState<ValidatedArea | null>(null)
  const [areaError, setAreaError] = useState('')
  const [checkingArea, setCheckingArea] = useState(false)
  const [apiStatus, setApiStatus] = useState<ApiStatus>('checking')
  const [liveEnabled, setLiveEnabled] = useState(false)
  const [historicalExamples, setHistoricalExamples] = useState<DemoEvent[]>([])
  const [chosenExampleSlug, setChosenExampleSlug] = useState('')
  const [limit, setLimit] = useState<number | null>(null)
  const [window, setWindow] = useState<(typeof windows)[number]>(30)
  const [dateMode, setDateMode] = useState<'event' | 'range'>('event')
  const [eventDate, setEventDate] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const activeRequest = useRef<AbortController>(null)
  const guide = useRef<HTMLDialogElement>(null)
  const { job, pending, source, error, submit, dismiss } = useAnalysis()

  useEffect(() => {
    const controller = new AbortController()
    getHealth(controller.signal).then((health) => {
      setApiStatus('online')
      setLimit(health.max_aoi_km2)
      setLiveEnabled(health.analysis_available)
    }).catch(() => { if (!controller.signal.aborted) setApiStatus('unavailable') })
    getDemoEvents(controller.signal).then((events) => {
      setHistoricalExamples(events.filter((event) => event.source === 'cached'))
    }).catch(() => {
      if (!controller.signal.aborted) setHistoricalExamples([])
    })
    return () => { controller.abort(); activeRequest.current?.abort() }
  }, [])

  function selectLocation(next: Location) {
    dismiss()
    setLocation(next)
    setLocationRevision((revision) => revision + 1)
  }

  function replaceBoundary(next: Polygon | null) {
    dismiss()
    activeRequest.current?.abort()
    setGeometry(next)
    setCheckedArea(null)
    setAreaError('')
    setCheckingArea(false)
  }

  function showLandBoundary(aoi: Polygon) {
    const ring = aoi.coordinates[0]
    const longitude = ring.map(point => point[0])
    const latitude = ring.map(point => point[1])
    const west = Math.min(...longitude), east = Math.max(...longitude)
    const south = Math.min(...latitude), north = Math.max(...latitude)
    replaceBoundary(aoi)
    selectLocation({ name: 'Land study area', region: 'Selected boundary', center: [(south + north) / 2, (west + east) / 2],
      zoom: Math.max(north - south, east - west) > 0.06 ? 12 : 14 })
    document.getElementById('map-heading')?.scrollIntoView({ block: 'start' })
  }

  async function checkBoundary() {
    if (!geometry) return
    const controller = new AbortController()
    activeRequest.current?.abort()
    activeRequest.current = controller
    setCheckingArea(true)
    setAreaError('')
    try {
      const validated = await validateArea(geometry, controller.signal)
      if (controller.signal.aborted) return
      setCheckedArea(validated)
      setLimit(validated.max_area_km2)
      setApiStatus('online')
    } catch (error) {
      if (!controller.signal.aborted) {
        setAreaError(error instanceof TypeError ? 'The analysis service is unavailable. Try again shortly.'
          : error instanceof Error ? error.message : 'The boundary could not be checked. Try again.')
      }
    } finally {
      if (activeRequest.current === controller) {
        activeRequest.current = null
        setCheckingArea(false)
      }
    }
  }

  const apiLabel = { checking: 'Connecting…', online: 'Analysis service online', unavailable: 'Analysis service unavailable' }[apiStatus]
  const result = job?.result
  const historicalExample = historicalExamples.find((event) => event.slug === chosenExampleSlug) ?? historicalExamples[0]
  let analysisWindow: Window | null = null
  if (window !== 'custom') analysisWindow = { kind: 'preset', days: window }
  else if (eventDate && dateMode === 'event') analysisWindow = { kind: 'event', date: eventDate }
  else if (startDate && startDate < eventDate && eventDate <= endDate) {
    analysisWindow = { kind: 'range', start: startDate, event: eventDate, end: endDate }
  }
  const statusTitle = job?.status === 'no_comparable_pair' ? 'No comparable pair'
    : error || job?.status === 'failed' ? 'Analysis unavailable'
    : liveEnabled ? 'Earth Engine configured' : 'Live Sentinel-1 access pending'
  const statusDetail = error || job?.message || (liveEnabled ? 'Validate a boundary and select a window to start a live analysis.'
      : historicalExample ? 'Open a historical example to explore satellite observations offline.'
      : 'Try the synthetic example to explore the workflow offline.')

  return <>
    <a className="skip-link" href="#workspace">Skip to workspace</a>
    <header className="topbar">
      <div className="topbar-content">
        <div className="brand"><span className="brand-icon"><Radar size={24} strokeWidth={1.7} /></span><span>SAR<span className="brand-light"> Translator</span></span></div>
        <div className="topbar-actions">
          <span className={`api-status ${apiStatus}`} role="status"><i />{apiLabel}</span>
          <button type="button" className="guide-button" onClick={() => guide.current?.showModal()}><CircleHelp size={17} /><span>Guide</span></button>
        </div>
      </div>
    </header>

    <main id="workspace" className="page">
      <div className="page-heading">
        <div>
          <h1>Flood analysis</h1>
          <p>Compare Sentinel-1 observations to see where surface water may have expanded.</p>
        </div>
        <div className="example-actions">
          {historicalExample && <div className="historical-example">
            <label>Historical example
              <select value={historicalExample.slug} onChange={(event) => setChosenExampleSlug(event.target.value)}>
                {historicalExamples.map((event) => <option key={event.slug} value={event.slug}>{event.title}</option>)}
              </select>
            </label>
            <button className="guide-button example-button" type="button" disabled={pending || apiStatus !== 'online'}
              aria-label="Open historical example" onClick={() => submit({ source: 'cached', slug: historicalExample.slug })}>
              <Archive size={17} /> Open offline
            </button>
          </div>}
          <button className="guide-button example-button" type="button" disabled={pending || apiStatus !== 'online'}
            onClick={() => submit({ source: 'synthetic' })}><FlaskConical size={18} /> Run synthetic example</button>
          <a className="guide-button example-button land-jump" href="#land-analysis"><Sprout size={17} /> Land analysis</a>
        </div>
      </div>

      {result && <FloodSummary result={result} onClose={dismiss} />}
      {pending && (source === 'cached'
        ? <AnalysisProgress title="Opening historical flood result" steps={[{ label: 'Load the archive', detail: 'Retrieving the saved radar maps and measurements.' }]} floating />
        : <AnalysisProgress title={source === 'synthetic' ? 'Running the practice analysis' : 'Analyzing Sentinel-1 radar'}
          context={source === 'synthetic' ? 'Synthetic practice data' : 'Surface-water change'}
          steps={source === 'synthetic' ? floodSteps.map((step, index) => ({ ...step, detail: [
            'Submitting the synthetic practice case.', 'Preparing paired practice observations.',
            'Running water-change detection on the generated pixels.', 'Rendering the practice comparison maps.',
          ][index] })) : floodSteps}
          current={job?.stage ? floodStageIndex[job.stage] : 0} floating />)}
      <div className="workspace-grid">
        <StudyMap location={location} locationRevision={locationRevision} geometry={geometry}
          areaValidated={checkedArea !== null} result={result ?? null} onGeometry={replaceBoundary} />

        <aside className="panel setup-panel" aria-labelledby="setup-heading">
          <div className="setup-heading"><Scan size={19} /><h2 id="setup-heading">Analysis setup</h2></div>

          <section className="setup-section" aria-labelledby="area-heading">
            <h3 id="area-heading"><MapPin size={17} /> Study area</h3>
            <LocationSearch onSelect={selectLocation} />
            <div className="area-card">
              <div className="area-icon"><Scan size={20} /></div>
              <div aria-live="polite">
                <span className="area-label">Boundary</span>
                <p>{checkedArea ? `${checkedArea.area_km2 < 0.001 ? '< 0.001' : areaNumber.format(checkedArea.area_km2)} km²`
                  : geometry ? 'Ready to validate' : 'No boundary drawn'}</p>
              </div>
              {geometry && <button className="clear-button" type="button" aria-label="Clear boundary" title="Clear boundary" onClick={() => replaceBoundary(null)}><X size={17} /></button>}
            </div>
            <p className="support-text" id="drawing-guide">Draw with the map tools. You can also pan with arrow keys and place points with Enter.</p>
          </section>

          <section className="setup-section window-section" aria-labelledby="window-heading">
            <h3 id="window-heading"><CalendarDays size={17} /> Time window</h3>
            <div className="window-options" role="group" aria-label="Observation window">
              {windows.map((option) => <button key={option} type="button" aria-pressed={window === option}
                onClick={() => setWindow(option)}>{option === 'custom' ? 'Custom' : `${option} days`}</button>)}
            </div>
            {window === 'custom' ? <>
              <label className="date-label">Custom window<select value={dateMode}
                onChange={(event) => setDateMode(event.target.value === 'range' ? 'range' : 'event')}>
                <option value="event">Around an event date</option><option value="range">Date range</option>
              </select></label>
              <label className="date-label">Event date<input type="date" value={eventDate} onChange={(event) => setEventDate(event.target.value)} /></label>
              {dateMode === 'range' ? <div className="date-range">
                <label className="date-label">Start date<input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label>
                <label className="date-label">End date<input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
              </div> : <p className="support-text">Compares 30 days before the event with 12 days starting on the event date.</p>}
            </> : <p className="support-text">The window ends on the latest usable observation date.</p>}
          </section>

          <div className="setup-action">
            <button className={checkedArea ? 'primary-button is-validated' : 'primary-button'}
              type="button" disabled={!geometry || checkingArea || !!checkedArea} onClick={checkBoundary}>
              <ShieldCheck size={18} /> {checkingArea ? 'Validating area…' : checkedArea ? 'Area validated' : 'Validate study area'}
            </button>
            {liveEnabled && <button className="primary-button live-run" type="button" disabled={!geometry || !checkedArea || !analysisWindow || pending}
              onClick={() => { if (geometry && analysisWindow) void submit({ source: 'earth_engine', aoi: geometry, window: analysisWindow }) }}>
              <Satellite size={18} /> Run Sentinel-1 analysis
            </button>}
            {limit !== null && <p className="area-limit">Maximum study area {areaNumber.format(limit)} km²</p>}
            {areaError && <p className="area-error" role="alert">{areaError}</p>}
          </div>
        </aside>
      </div>

      {result ? <Results key={result.id} result={result} rejections={job.rejections} /> : !pending && <section className="analysis-status" aria-labelledby="analysis-status-heading" aria-live="polite">
        <div className="status-icon"><Satellite size={22} strokeWidth={1.7} /></div>
        <div><h2 id="analysis-status-heading">{statusTitle}</h2><p>{statusDetail}</p>
          {job && <PairingDetails rejections={job.rejections} />}
        </div>
      </section>}
      <LandWorkspace area={checkedArea ? geometry : null} liveEnabled={liveEnabled} showOnMap={showLandBoundary} />
    </main>

    <dialog className="guide" ref={guide} aria-labelledby="guide-heading">
      <div className="guide-heading"><h2 id="guide-heading">Workspace guide</h2><form method="dialog"><button type="submit" aria-label="Close guide"><X size={20} /></button></form></div>
      <ol>
        <li>Choose an example location or pan the regional map to your study area.</li>
        <li>Zoom in and choose the rectangle or polygon tool. For a rectangle, select opposite corners. For a polygon, place at least three points, then select Finish polygon.</li>
        <li>Choose a time window and validate the boundary. The area is measured in square kilometres on the WGS84 ellipsoid.</li>
        <li>Open a historical example to explore archived Sentinel-1 observations, or run a synthetic example to practice. Compare the map layers and download the evidence report.</li>
      </ol>
      <p>Keyboard drawing uses the map center. Press Enter to place a point, Shift+Enter to finish a polygon, or Escape to cancel.</p>
    </dialog>
  </>
}
