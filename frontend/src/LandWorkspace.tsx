import { useEffect, useRef, useState, type FormEvent } from 'react'
import type { Polygon } from 'geojson'
import { CloudRain, Download, Droplet, Leaf, MapPin, Pause, Play, Sprout, Sun, Wheat } from 'lucide-react'
import { apiUrl } from './api'
import { AnalysisProgress } from './AnalysisProgress'
import { ComparePlots, SatelliteEvidence } from './LandEvidence'
import { TerrainView } from './TerrainView'
import { createLandProfile, generateLandNarrative, getLandCatalog, getLandGuidance, getLandProfile, landPurposes, landRoles, simulateLand,
  type LandDemo, type LandFocus, type LandGuidance, type LandObservation, type LandProfile, type LandStage, type Scenario, type ScenarioInput } from './landApi'
import './land.css'

const monthFormat = new Intl.DateTimeFormat('en', { month: 'short', year: 'numeric', timeZone: 'UTC' })
const month = (day: string) => monthFormat.format(new Date(day))
const metric = (value: number | null, suffix = '') => value === null ? 'Unavailable' : `${value}${suffix}`
const detail = (error: unknown) => error instanceof Error ? error.message : 'The request could not be completed.'
const landSteps = [
  { label: 'Check the study boundary', detail: 'The server is validating the boundary and time window.' },
  { label: 'Read satellite sources', detail: 'Looking up Sentinel-2 acquisition dates and regional SMAP moisture observations.' },
  { label: 'Measure the selected area', detail: 'Sampling cloud-screened vegetation, moisture, water and Dynamic World land cover.' },
  { label: 'Assemble the timeline', detail: 'Calculating monthly measurements and preparing the satellite previews.' },
] as const
const landStageIndex = { sources: 1, pixels: 2, summary: 3 }
const aiSteps = [{ label: 'Generate suggestion from measurements', detail: 'The configured AI provider is reviewing the derived observations.' }] as const

const trendMetrics = [
  { key: 'ndvi', label: 'Plant greenness', unit: 'NDVI', icon: Leaf, description: 'Higher values generally mean greener plants.' },
  { key: 'ndmi', label: 'Water in plants', unit: 'NDMI', icon: Droplet, description: 'Higher values usually mean plants contain more water. Satellites estimate this from reflected light.' },
  { key: 'soil_moisture_pct', label: 'Soil moisture nearby', unit: '%', icon: CloudRain, description: 'The SMAP satellite estimates soil moisture for the surrounding area using a grid about 11 km wide.' },
] as const

function TimeBars({ label, points, min, max, suffix, selected, onSelect }: {
  label: string; points: { label: string; value: number | null }[]; min: number; max: number; suffix: string
  selected: number; onSelect: (index: number) => void
}) {
  const zero = -min * 100 / (max - min)
  return <div className="land-chart-layout">
    <div className="land-chart-axis" aria-hidden="true"><span>{max}{suffix}</span><span>{(max + min) / 2}{suffix}</span><span>{min}{suffix}</span></div>
    <div className="land-chart-scroll">
      <div className="land-months" role="group" aria-label={label}>
        {points.map(({ label: pointLabel, value }, index) => <button key={pointLabel} type="button" aria-pressed={selected === index} onClick={() => onSelect(index)}>
          <span className="land-chart-track" aria-hidden="true">
            <span className="land-zero-line" style={{ bottom: `${zero}%` }} />
            {value !== null && <i style={{ bottom: `${(Math.min(0, value) - min) * 100 / (max - min)}%`, height: `${Math.abs(value) * 100 / (max - min)}%` }} />}
          </span>
          <span className="land-month-label"><strong>{value === null ? 'No data' : `${value}${suffix}`}</strong><span>{pointLabel}</span></span>
        </button>)}
      </div>
    </div>
  </div>
}

function LandTrend({ observations, selected, onSelect, purpose }: {
  observations: LandObservation[]; selected: number; onSelect: (index: number) => void; purpose: LandFocus['purpose']
}) {
  const [key, setKey] = useState<(typeof trendMetrics)[number]['key']>(purpose === 'water' ? 'soil_moisture_pct' : 'ndvi')
  const current = trendMetrics.find(item => item.key === key) ?? trendMetrics[0]
  const values = observations.map(item => item[current.key])
  const suffix = current.unit === '%' ? '%' : ''
  const max = suffix ? 100 : 1
  const min = values.some(value => value !== null && value < 0) ? -1 : 0

  return <section className="panel land-trend" aria-labelledby="timeline-heading">
    <div className="land-section-head"><h3 id="timeline-heading">Changes over time</h3><span>{month(observations[0].start)} – {month(observations[observations.length - 1].start)}</span></div>
    <div className="land-stat-cards" role="group" aria-label="Chart measurement">
      {trendMetrics.map(({ key: measurement, icon: Icon, label, unit }) => <button key={measurement} type="button"
        className={`land-stat land-stat-${measurement}`} aria-pressed={key === measurement} onClick={() => setKey(measurement)}>
        <Icon size={17} aria-hidden="true" /><span>{label}</span>
        <strong>{metric(observations[selected][measurement], unit === '%' ? '%' : '')}</strong>
        <small>{unit === '%' ? 'Regional estimate' : unit}</small>
      </button>)}
    </div>
    <div className="land-chart" data-metric={current.key}>
      <div className="land-chart-heading"><strong>{current.label}</strong><span>{current.description}</span></div>
      <TimeBars label={`Monthly ${current.label.toLowerCase()}`} points={observations.map((item, index) => ({ label: month(item.start), value: values[index] }))}
        min={min} max={max} suffix={suffix} selected={selected} onSelect={onSelect} />
      <p className="support-text">Select a month to update the satellite image and land cover below.</p>
    </div>
  </section>
}

function useLandRequest() {
  const controller = useRef<AbortController | null>(null)
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState('')
  useEffect(() => () => controller.current?.abort(), [])

  async function run<T>(operation: (signal: AbortSignal) => Promise<T>, done: (result: T) => void) {
    controller.current?.abort()
    const active = new AbortController()
    controller.current = active
    setMessage('')
    setPending(true)
    try {
      const response = await operation(active.signal)
      if (!active.signal.aborted) done(response)
    } catch (error) {
      if (!active.signal.aborted) setMessage(detail(error))
    } finally {
      if (controller.current === active) {
        controller.current = null
        setPending(false)
      }
    }
  }
  return { run, pending, message }
}

const scenarioFields = [
  { key: 'rain_mm_week', label: 'Rain each week (mm)', min: 0, max: 300 },
  { key: 'demand_mm_day', label: 'Water lost each day (mm)', min: 0, max: 15 },
  { key: 'storage_capacity_mm', label: 'How much water the soil can hold (mm)', min: 20, max: 300 },
  { key: 'initial_storage_pct', label: 'How full the soil is at the start (%)', min: 0, max: 100 },
] as const
const droughtValues: ScenarioInput = { days: 28, rain_mm_week: 2, demand_mm_day: 3, storage_capacity_mm: 100, initial_storage_pct: 50 }
const rainfallValues: ScenarioInput = { ...droughtValues, rain_mm_week: 85 }

function ScenarioPanel({ profile, active, liveEnabled }: { profile: LandProfile; active: boolean; liveEnabled: boolean }) {
  const [values, setValues] = useState(droughtValues)
  const [outcome, setOutcome] = useState<Scenario | null>(null)
  const [selected, setSelected] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [mapMode, setMapMode] = useState<'2d' | '3d'>('2d')
  const [useMonsoon, setUseMonsoon] = useState(false)
  const [monsoonYear, setMonsoonYear] = useState(2024)
  const { run, pending, message } = useLandRequest()
  const frameCount = outcome?.frames.length ?? 0

  useEffect(() => {
    if (!active || !playing || frameCount < 2) return
    const timer = window.setInterval(() => setSelected(index => (index + 1) % frameCount), 850)
    return () => window.clearInterval(timer)
  }, [active, playing, frameCount])

  function submit(event: FormEvent) {
    event.preventDefault()
    setPlaying(false)
    const inputs = useMonsoon ? { ...values, rain_mm_week: 0 } : values
    const year = useMonsoon ? (liveEnabled ? monsoonYear : 2024) : undefined
    void run(signal => simulateLand(profile.id, inputs, signal, year), (result) => {
      setOutcome(result)
      setSelected(result.frames.length - 1)
    })
  }

  const frame = outcome?.frames[selected]
  const terrainStorage = frame?.terrain_storage_pct
  const recorded = outcome?.recorded_rain
  const weekRain = recorded && frame && frame.day > 0 ? recorded.daily_mm.slice(frame.day - 7, frame.day) : null
  function selectFrame(index: number) {
    setPlaying(false)
    setSelected(index)
  }

  return <section className="panel land-scenario" aria-labelledby="scenario-heading">
    <div className="land-subheading"><CloudRain size={19} /><h3 id="scenario-heading">Rainfall and drought scenarios</h3></div>
    <p className="support-text">Try a dry spell or heavy rain to see how much water the soil might hold. Results are estimates based on the amounts you enter.</p>
    {profile.scenario_period ? <div className="land-scenario-grid">
      <form className="panel scenario-input-card" onSubmit={submit}>
        <h4>Choose rainfall and soil settings</h4>
        <div className="layer-buttons land-controls">
          <button type="button" onClick={() => { setUseMonsoon(false); setValues(droughtValues) }}>Drought preset</button>
          <button type="button" onClick={() => { setUseMonsoon(false); setValues(rainfallValues) }}>Heavy rain preset</button>
          <button type="button" aria-pressed={useMonsoon} onClick={() => setUseMonsoon(!useMonsoon)}>Use past monsoon rain</button>
        </div>
        <div className="land-fields">
          {useMonsoon && (liveEnabled
            ? <label>Monsoon year<input type="number" required min={1981} max={new Date().getFullYear()} value={Number.isNaN(monsoonYear) ? '' : monsoonYear}
              onChange={event => setMonsoonYear(event.target.valueAsNumber)} /></label>
            : <p className="support-text">Offline replay uses rain from July 2024.</p>)}
          {scenarioFields.filter(field => !useMonsoon || field.key !== 'rain_mm_week').map(({ key, label, min, max }) => <label key={key}>{label}
            <input type="number" min={min} max={max} step="any" value={Number.isNaN(values[key]) ? '' : values[key]} required
              onChange={event => setValues(previous => ({ ...previous, [key]: event.target.valueAsNumber }))} />
          </label>)}
          <label>Duration<select value={values.days} onChange={event => setValues(previous => ({ ...previous, days: Number(event.target.value) }))}>
            <option value="14">14 days</option><option value="28">28 days</option><option value="42">42 days</option>
          </select></label>
        </div>
        <button type="submit" className="primary-button" disabled={pending}>{pending ? 'Running scenario…' : useMonsoon ? 'Replay monsoon' : 'Run scenario'}</button>
        {pending && <AnalysisProgress title="Estimating soil water"
          steps={[{ label: 'Estimate soil water each week', detail: 'Using your rain and water loss settings to prepare the weekly maps.' }]} />}
        {useMonsoon && <p className="support-text">Starts on July 1. Daily rain comes from the CHIRPS grid near this plot. Soil water is estimated using your settings.</p>}
        <p className="support-text">The model uses the satellite land-cover map from {month(profile.scenario_period)} to estimate how much rain soaks in.</p>
        <details className="result-details"><summary>How the estimate works</summary>
          <p className="support-text">For the presets, the model spreads rain evenly across the week. A past monsoon uses the rain estimate for each day. The model adds the rain that soaks in, counts water above the soil limit as excess, then subtracts the daily water loss. It assumes 80% soaks in on tree-covered land, 75% on grass, 70% on crops, 65% on shrub and scrub, 45% on bare ground, and 15% in built-up areas. It skips water, flooded vegetation, snow, and places where the land type is unknown.</p>
        </details>
        {message && <p className="area-error" role="alert">{message}</p>}
      </form>
      {frame && outcome && <div className="land-scenario-result">
        {recorded && <div className="panel evidence-patch">
          <strong>Past monsoon · starting {recorded.start}</strong>
          <p>{weekRain ? `${weekRain.reduce((sum, rain) => sum + rain, 0).toFixed(1)} mm of rain in the 7 days through Day ${frame.day}`
            : 'Starting soil conditions, before the first day’s rain'}</p>
          <p className="support-text">Regional rainfall estimates from <a href="https://developers.google.com/earth-engine/datasets/catalog/UCSB-CHG_CHIRPS_DAILY">CHIRPS</a> (about 5 km grid). The soil-water values below are a simulation.</p>
        </div>}
        <div className="land-chart scenario-chart" data-metric="soil_moisture_pct">
          <div className="land-chart-heading"><strong>How full the soil is each week</strong><span>50% means the soil holds half as much water as it can in this scenario. Pick a day to see it on the map.</span></div>
          <TimeBars label="Weekly soil water estimates" points={outcome.frames.map(item => ({ label: `Day ${item.day}`, value: item.mean_storage_pct }))}
            min={0} max={100} suffix="%" selected={selected} onSelect={selectFrame} />
        </div>
        <dl className="land-values scenario-values">
          <div><dt>How full the soil is</dt><dd>{frame.mean_storage_pct}%</dd><dd className="scenario-value-note">Average across the land included</dd></div>
          <div><dt>Land low on soil water</dt><dd>{frame.low_storage_area_pct}%</dd><dd className="scenario-value-note">Share of land where the soil is less than 25% full</dd></div>
          <div><dt>Water the soil couldn’t hold</dt><dd>{frame.mean_overflow_mm} mm</dd><dd className="scenario-value-note">Average excess since the start</dd></div>
        </dl>
        <div className="layer-buttons scenario-map-switch" role="group" aria-label="Scenario map view">
          <button type="button" aria-pressed={mapMode === '2d' || !terrainStorage} onClick={() => setMapMode('2d')}>2D map</button>
          {terrainStorage && <button type="button" aria-pressed={mapMode === '3d'} onClick={() => setMapMode('3d')}>3D replay</button>}
        </div>
        <div className="land-playback">
          <button type="button" className="guide-button" onClick={() => { if (!playing) setSelected(0); setPlaying(!playing) }}>
            {playing ? <Pause size={15} /> : <Play size={15} />}{playing ? 'Pause' : 'Play'}
          </button>
          <label>Day {frame.day}<input type="range" aria-label="Day in the scenario" aria-valuetext={`Day ${frame.day}`} min={0} max={frameCount - 1} value={selected}
            onChange={event => selectFrame(Number(event.target.value))} /></label>
        </div>
        {mapMode === '3d' && terrainStorage ? <TerrainView id={profile.id} storage={terrainStorage} day={frame.day} /> : <>
          <figure className="land-image land-storage-image">
            <img alt={`Map of estimated soil water on day ${frame.day}`} src={frame.image} />
            <figcaption>Estimated soil water · Day {frame.day}</figcaption>
          </figure>
          <div aria-label="Soil water scale from empty to full" className="land-scale"><span>0% · Empty</span><i /><span>100% · Full</span></div>
        </>}
        <p className="support-text">This run uses {recorded ? 'past daily rainfall' : `${outcome.inputs.rain_mm_week} mm of rain per week`} and {outcome.inputs.demand_mm_day} mm of water loss per day. {mapMode === '2d' && 'Blank areas have no estimate.'}</p>
      </div>}
    </div> : <p className="support-text">The satellite data needs to identify more of the land here before you can run a scenario.</p>}
  </section>
}

function ObservationPanel({ snapshot, grid }: { snapshot: LandObservation; grid: number }) {
  const classes = Object.entries(snapshot.land_cover_pct).filter(([, value]) => value > 0).sort((a, b) => b[1] - a[1])
  return <div className="land-observation">
    <figure className="land-image">
      {snapshot.image ? <img src={snapshot.image} alt={`Sentinel-2 natural-color composite for ${month(snapshot.start)}`} />
        : <div className="land-image-empty">No clear image</div>}
      <figcaption>Sentinel-2 · {month(snapshot.start)} · north up</figcaption>
    </figure>
    <div className="panel land-observation-data">
      <h3>Land cover in {month(snapshot.start)}</h3>
      {classes.length > 0 && <p className="land-leading"><strong>{classes[0][1]}%</strong> {classes[0][0].toLowerCase()}</p>}
      <p className="support-text">Dynamic World could identify the land type for {snapshot.classified_pct}% of the study area. The breakdown below covers that part.</p>
      {classes.length ? <ul className="land-cover">
        {classes.slice(0, 3).map(([name, value]) => <li key={name}><span>{name}</span><meter min={0} max={100} value={value} aria-label={name} /><span>{value}%</span></li>)}
      </ul> : <p className="support-text">The satellite data could not reliably identify the land type this month.</p>}
      <details className="panel evidence-details land-observation-details">
      <summary>More measurements and satellite image dates</summary>
      <p className="support-text">{snapshot.start} to {snapshot.end} · Clear imagery for {snapshot.clear_pct}% of the study area · {grid} m grid</p>
      <dl className="land-values">
        <div><dt>Vegetation greenness (NDVI)</dt><dd>{metric(snapshot.ndvi)}</dd></div>
        <div><dt>Estimated water in plants (NDMI)</dt><dd>{metric(snapshot.ndmi)}</dd></div>
        <div><dt>Water visible in satellite imagery</dt><dd>{metric(snapshot.mapped_water_pct, '%')}</dd></div>
        <div><dt>Regional soil moisture (SMAP)</dt><dd>{metric(snapshot.soil_moisture_pct, '%')}</dd></div>
      </dl>
      {classes.length > 3 && <ul className="land-cover">
        {classes.slice(3).map(([name, value]) => <li key={name}><span>{name}</span><meter min={0} max={100} value={value} aria-label={name} /><span>{value}%</span></li>)}
      </ul>}
      <details className="result-details">
        <summary>How much the images appear to shift</summary>
        <p className="support-text">{snapshot.image_offset
          ? `${snapshot.image_offset.east_m} m east and ${snapshot.image_offset.north_m} m north compared with ${month(snapshot.image_offset.from_period)}. ${snapshot.image_offset.matched_blocks} patches in the images showed the same shift.`
          : 'No reliable image shift was found for this period.'} The comparison uses the satellite grid. Separate measurements are needed to confirm whether the ground moved.</p>
      </details>
      <details className="result-details">
        <summary>Sentinel-2 image dates ({snapshot.scenes.length})</summary>
        <ul>{snapshot.scenes.map(scene => <li key={scene.id}><time dateTime={scene.acquired_at}>{scene.acquired_at.slice(0, 16).replace('T', ' ')} UTC</time> · {scene.id.split('/').at(-1)}</li>)}</ul>
      </details>
      </details>
    </div>
  </div>
}

const resultViews = { overview: 'Overview', satellite: 'Satellite data', inspection: 'Field inspection', compare: 'Compare plots',
  history: '30 years ago', terrain: '3D terrain', scenario: 'Scenarios', report: 'Report' } as const

function LandOverview({ profile, focus, aiAvailable, openData, openScenario }: {
  profile: LandProfile; focus: LandFocus; aiAvailable: boolean; openData: () => void; openScenario: () => void
}) {
  const [guidance, setGuidance] = useState<LandGuidance | null>(null)
  const [loadingAi, setLoadingAi] = useState(false)
  const [error, setError] = useState('')
  const { run, pending, message } = useLandRequest()

  useEffect(() => {
    const request = new AbortController()
    async function load() {
      try {
        const measured = await getLandGuidance(profile.id, focus, false, request.signal)
        if (request.signal.aborted) return
        setGuidance(measured)
        if (aiAvailable) {
          setLoadingAi(true)
          const personalized = await getLandGuidance(profile.id, focus, true, request.signal)
          if (!request.signal.aborted) setGuidance(personalized)
        }
      } catch (failure) {
        if (!request.signal.aborted) setError(detail(failure))
      } finally {
        if (!request.signal.aborted) setLoadingAi(false)
      }
    }
    void load()
    return () => request.abort()
  }, [profile.id, focus, aiAvailable])

  const canRetry = aiAvailable && guidance && !guidance.narrative && !loadingAi
  return <section className="panel land-guidance" aria-labelledby="guidance-heading">
    <h4 id="guidance-heading">What to look at for your purpose</h4>
    {guidance ? <div className="land-guidance-grid">
      <div className="land-evidence-card"><h5>What the satellite data shows</h5><p>{guidance.evidence}</p>
        <button className="guide-button" type="button" onClick={openData}>{focus.purpose === 'site' ? 'See land cover' : 'See satellite data'}</button>
        {focus.purpose === 'water' && profile.scenario_period && <button className="guide-button" type="button" onClick={openScenario}>Explore rainfall scenarios</button>}
      </div>
      <div className="land-checks-card"><h5>What to verify</h5><ul>{guidance.checks.map(check => <li key={check}>{check}</li>)}</ul></div>
    </div> : !error && <AnalysisProgress title="Preparing your land overview" context={landPurposes[focus.purpose]}
      steps={[{ label: 'Match evidence to your purpose', detail: 'Selecting relevant satellite measurements and checks for your role.' }]} />}
    {guidance?.narrative && <div className="land-ai-notes"><h5>Personalized AI suggestion</h5><p>{guidance.narrative.text}</p></div>}
    {(loadingAi || pending) && <AnalysisProgress ai title="Writing your personalized suggestion" context={landRoles[focus.role]} steps={aiSteps} />}
    {guidance && !guidance.narrative && !loadingAi && <p className="support-text">Guidance based on your selected role and purpose.{!aiAvailable ? ' Live AI is unavailable in this session.' : ''}</p>}
    {canRetry && <button className="guide-button" type="button" disabled={pending} onClick={() => {
      setError('')
      void run(signal => getLandGuidance(profile.id, focus, true, signal), setGuidance)
    }}>{pending ? 'Generating suggestion…' : 'Retry AI suggestion'}</button>}
    {(error || message) && <p className="area-error" role="alert">{error || message}</p>}
  </section>
}

function LandResults({ profile, focus, aiAvailable, showOnMap, demos, recent, liveEnabled }: {
  profile: LandProfile; focus: LandFocus; aiAvailable: boolean; showOnMap: (aoi: Polygon) => void
  demos: LandDemo[]; recent: { id: string; title: string }[]; liveEnabled: boolean
}) {
  const latest = profile.observations.map(snapshot => snapshot.ndvi !== null).lastIndexOf(true)
  const [selected, setSelected] = useState(latest < 0 ? profile.observations.length - 1 : latest)
  const [narrative, setNarrative] = useState(profile.narrative)
  const [view, setView] = useState<keyof typeof resultViews>('overview')
  const [terrainOpened, setTerrainOpened] = useState(false)
  const resultHeading = useRef<HTMLHeadingElement>(null)
  const { run, pending, message } = useLandRequest()
  const snapshot = profile.observations[selected]
  const observation = snapshot && <ObservationPanel snapshot={snapshot} grid={profile.grid_m} />
  useEffect(() => {
    setView('overview')
    resultHeading.current?.focus({ preventScroll: true })
    resultHeading.current?.scrollIntoView({ block: 'start' })
  }, [profile])

  return <div className="land-results" id="land-results">
    <header className="panel land-result-header">
      <div><h3 ref={resultHeading} tabIndex={-1}>{profile.title}</h3>
        <p className="support-text">{profile.area_km2.toFixed(2)} km² · {profile.terrain ? 'Offline satellite archive' : 'Live Earth Engine result'}</p>
        <p className="support-text"><strong>{landRoles[focus.role]}</strong> · {landPurposes[focus.purpose]}</p>
      </div>
      <div className="land-result-actions">
        <button type="button" className="guide-button" onClick={() => showOnMap(profile.aoi)}><MapPin size={15} /> Show boundary on map</button>
        <a className="guide-button land-jump" href="#purpose-heading">Change focus</a>
      </div>
    </header>
    <div className="land-view-switch" role="group" aria-label="Land result view">
      {(Object.keys(resultViews) as (keyof typeof resultViews)[]).map(key => <button key={key} type="button" aria-pressed={view === key} onClick={() => {
        if (key === 'terrain') setTerrainOpened(true)
        setView(key)
      }}>{resultViews[key]}</button>)}
    </div>
    <div hidden={view !== 'overview'}><LandOverview profile={profile} focus={focus} aiAvailable={aiAvailable}
      openData={() => setView('satellite')} openScenario={() => setView('scenario')} /></div>
    {snapshot && <div className="land-view-content" hidden={view !== 'satellite'}>
      {focus.purpose === 'site' && observation}
      <LandTrend observations={profile.observations} selected={selected} onSelect={setSelected} purpose={focus.purpose} />
      {focus.purpose !== 'site' && observation}
      <p className="result-credit">Optical water includes existing water. Use Sentinel-1 analysis for event-specific flood screening.
        {' '}<a href="https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED">Sentinel-2</a> · <a href="https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1">Google/WRI Dynamic World</a> · <a href="https://developers.google.com/earth-engine/datasets/catalog/NASA_SMAP_SPL4SMGP_008">NASA SMAP L4</a></p>
    </div>}
    {(view === 'inspection' || view === 'history') && <SatelliteEvidence key={view} profile={profile} mode={view} />}
    {view === 'compare' && <ComparePlots profile={profile} demos={demos} recent={recent} />}
    {terrainOpened && <div hidden={view !== 'terrain'}><TerrainView id={profile.id} /></div>}
    <div hidden={view !== 'scenario'}><ScenarioPanel profile={profile} active={view === 'scenario'} liveEnabled={liveEnabled} /></div>
    <section className="panel land-report" aria-labelledby="land-report-heading" hidden={view !== 'report'}>
      <h3 id="land-report-heading">Land analysis report</h3>
      {narrative && <details className="result-details"><summary>{narrative.source === 'cached_ai' ? 'Cached AI-generated summary' : narrative.source === 'ai' ? 'AI-generated summary' : 'Template summary'}</summary>
        <p className="land-narrative">{narrative.text}</p></details>}
      <div className="land-report-actions">
        {!narrative && aiAvailable && <button className="guide-button" type="button" disabled={pending}
          onClick={() => void run(signal => generateLandNarrative(profile.id, signal), setNarrative)}>{pending ? 'Generating…' : 'Generate AI summary'}</button>}
        <a className="report-button" download href={apiUrl(`land/analyses/${encodeURIComponent(profile.id)}/report.pdf`)}><Download size={16} /> Download land PDF</a>
      </div>
      {pending && <AnalysisProgress ai title="Writing the land report summary" steps={aiSteps} />}
      {message && <p className="area-error" role="alert">{message}</p>}
    </section>
  </div>
}

export function LandWorkspace({ area, liveEnabled, showOnMap }: {
  area: Polygon | null; liveEnabled: boolean; showOnMap: (aoi: Polygon) => void
}) {
  const [demos, setDemos] = useState<LandDemo[]>([])
  const [aiAvailable, setAiAvailable] = useState(false)
  const [catalogFailed, setCatalogFailed] = useState(false)
  const [catalogAttempt, setCatalogAttempt] = useState(0)
  const [role, setRole] = useState<LandFocus['role'] | ''>('')
  const [purpose, setPurpose] = useState<LandFocus['purpose'] | ''>('')
  const [result, setResult] = useState<{ profile: LandProfile; focus: LandFocus } | null>(null)
  const [recent, setRecent] = useState<{ id: string; title: string }[]>([])
  const [operation, setOperation] = useState<'archive' | 'live'>('archive')
  const [landStage, setLandStage] = useState<LandStage | null>(null)
  const today = new Date().toISOString().slice(0, 10)
  const [end, setEnd] = useState(today)
  const [months, setMonths] = useState(6)
  const { run, pending, message } = useLandRequest()
  const focus = role && purpose ? { role, purpose } : null
  const changedFocus = result && focus && (result.focus.role !== role || result.focus.purpose !== purpose)

  useEffect(() => {
    const active = new AbortController()
    getLandCatalog(active.signal).then(catalog => {
      setDemos(catalog.demos)
      setAiAvailable(catalog.ai_available)
      setCatalogFailed(false)
    }).catch(() => { if (!active.signal.aborted) setCatalogFailed(true) })
    return () => active.abort()
  }, [catalogAttempt])

  return <section id="land-analysis" className="land-workspace" aria-labelledby="land-heading">
    <div className="land-subheading land-workspace-heading"><Sprout size={22} /><h2 id="land-heading">Land analysis</h2></div>
    <div className="land-setup-grid">
    <section className="panel land-focus" aria-labelledby="purpose-heading">
      <h3 id="purpose-heading">Choose your analysis focus</h3>
      <div className="land-live-form">
        <label>Who is analyzing?<select value={role} disabled={pending} onChange={event => setRole(event.target.value as typeof role)}>
          <option value="">Select a role</option>
          {Object.entries(landRoles).map(([key, name]) => <option key={key} value={key}>{name}</option>)}
        </select></label>
        <label>Purpose<select value={purpose} disabled={pending || !role} onChange={event => setPurpose(event.target.value as typeof purpose)}>
          <option value="">Select a purpose</option>
          {Object.entries(landPurposes).map(([key, name]) => <option key={key} value={key}>{name}</option>)}
        </select></label>
        {changedFocus && <button className="guide-button" type="button" disabled={pending}
          onClick={() => setResult({ profile: result.profile, focus })}>Update current analysis</button>}
      </div>
    </section>
    <section className="panel land-run" aria-labelledby="land-run-heading">
    <h3 id="land-run-heading">Choose the study area</h3>
    <p className="support-text">{focus ? 'Open a demo or analyze the validated boundary on the map.' : 'Select a role and purpose to enable the analysis.'}</p>
    <div className="land-demos">
      {demos.map(demo => <button className={`panel land-demo land-demo-${demo.terrain}`} key={demo.id} type="button" disabled={pending || !focus} aria-pressed={result?.profile.id === demo.id}
        onClick={() => {
          if (!focus) return
          setOperation('archive')
          void run(signal => getLandProfile(demo.id, signal), profile => setResult({ profile, focus }))
        }}>
        {demo.terrain === 'farmland' ? <Wheat size={20} aria-hidden="true" /> : <Sun size={20} aria-hidden="true" />}
        <span>{demo.terrain === 'farmland' ? 'Farmland demo' : 'Dry-land demo'}<small>{demo.title}</small></span>
      </button>)}
    </div>
    {catalogFailed && <div className="land-report-actions">
      <p className="support-text" role="status">The land demo catalog could not load.</p>
      <button className="guide-button" type="button" onClick={() => setCatalogAttempt(count => count + 1)}>Reload land demos</button>
    </div>}
    {liveEnabled && <form className="land-live-form" onSubmit={event => {
      event.preventDefault()
      if (!area || !focus) return
      setOperation('live')
      setLandStage(null)
      void run(signal => createLandProfile(area, end, months, signal, setLandStage), profile => {
        const [lng, lat] = profile.aoi.coordinates[0][0]
        const title = `Plot near ${lat.toFixed(4)}, ${lng.toFixed(4)} · through ${end}`
        setRecent(plots => [{ id: profile.id, title }, ...plots].slice(0, 10))
        setResult({ profile: { ...profile, title }, focus })
      })
    }}>
      <label>End date<input type="date" required value={end} min="2018-01-01" max={today} onChange={event => setEnd(event.target.value)} /></label>
      <label>Months<select value={months} onChange={event => setMonths(Number(event.target.value))}>
        <option value="3">3 months</option><option value="6">6 months</option><option value="12">12 months</option>
      </select></label>
      <button className="primary-button" disabled={pending || !area || !focus} type="submit">Run land analysis</button>
    </form>}
    </section>
    </div>
    {pending && (operation === 'live'
      ? <AnalysisProgress title="Analyzing satellite observations" context={`${months} months · ${role ? landRoles[role] : 'Land analysis'}`}
        steps={landSteps} current={landStage ? landStageIndex[landStage] : 0} floating />
      : <AnalysisProgress title="Opening the land archive" steps={[{ label: 'Read the stored observations', detail: 'Loading monthly imagery and measurements for the selected demo.' }]} floating />)}
    {message && <p className="area-error" role="alert">{message}</p>}
    {result && <LandResults key={`${result.profile.id}-${result.focus.role}-${result.focus.purpose}`} {...result}
      aiAvailable={aiAvailable} showOnMap={showOnMap} demos={demos} recent={recent} liveEnabled={liveEnabled} />}
  </section>
}
