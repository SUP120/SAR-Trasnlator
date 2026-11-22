import { useEffect, useState } from 'react'
import { getHistory, getInspection, getLandProfile, getPlotEvidence,
  type HistoryEvidence, type ImageEvidence, type InspectionEvidence, type LandDemo, type LandProfile, type PlotEvidence } from './landApi'

const month = new Intl.DateTimeFormat('en', { month: 'short', year: 'numeric', timeZone: 'UTC' })
const period = (date: string) => month.format(new Date(date))

function ImageSource({ evidence }: { evidence: ImageEvidence }) {
  return <details className="result-details">
    <summary>{evidence.start} to {evidence.end} · {evidence.clear_pct}% clear · {evidence.scenes.length} satellite images</summary>
    <ul>{evidence.scenes.map(scene => <li key={scene.id}>{scene.acquired_at.slice(0, 10)} · {scene.id}</li>)}</ul>
  </details>
}

function History({ history }: { history: HistoryEvidence }) {
  const [divider, setDivider] = useState(50)
  return <>
    <p className="support-text">Move the slider to compare the same three months, 30 years apart.</p>
    <div className="evidence-swipe land-image">
      <img src={history.recent.image} alt={`Landsat 8 and 9 imagery ending ${period(history.recent.end)}`} />
      <img className="evidence-layer" src={history.earlier.image} alt={`Landsat 5 imagery ending ${period(history.earlier.end)}`}
        style={{ clipPath: `inset(0 ${100 - divider}% 0 0)` }} />
      <span className="evidence-divider" aria-hidden="true" style={{ left: `${divider}%` }} />
    </div>
    <label className="evidence-slider">Earlier image shown <input type="range" min={0} max={100} value={divider}
      aria-valuetext={`${divider}% of the earlier image`} onChange={event => setDivider(Number(event.target.value))} /></label>
    <div className="land-evidence-pair">
      <div><strong>Landsat 5 · {period(history.earlier.end)}</strong><ImageSource evidence={history.earlier} /></div>
      <div><strong>Landsat 8 and 9 · {period(history.recent.end)}</strong><ImageSource evidence={history.recent} /></div>
    </div>
    <p className="support-text">{history.grid_m} m detail. Blank spots have no clear image. Differences in color can come from the sensors or conditions on the day.</p>
  </>
}

function Inspection({ evidence }: { evidence: InspectionEvidence }) {
  const [selected, setSelected] = useState<number | null>(evidence.patches[0]?.id ?? null)
  const [year, setYear] = useState(evidence.earlier[evidence.earlier.length - 1]?.start ?? '')
  const earlier = evidence.earlier.find(image => image.start === year)
  const patch = evidence.patches.find(item => item.id === selected)
  return <>
    <p className="support-text">Orange patches got less green than in the same month of earlier years. Select a patch to see where to check on the ground.</p>
    <div className="land-evidence-pair">
      <div>
        <label className="evidence-image-label">Earlier satellite image <select value={year} onChange={event => setYear(event.target.value)}>
          {evidence.earlier.map(image => <option key={image.start} value={image.start}>{period(image.start)}</option>)}
        </select></label>
        {earlier && <><figure className="land-image evidence-marked"><img src={earlier.image} alt={`Earlier satellite view for ${period(earlier.start)}`} /></figure>
          <ImageSource evidence={earlier} /></>}
      </div>
      <div>
        <strong className="evidence-image-label">Recent satellite image · {period(evidence.recent.start)}</strong>
        <figure className="land-image evidence-marked">
          <img src={evidence.recent.image} alt={`Recent satellite view for ${period(evidence.recent.start)}`} />
          <img className="evidence-layer" src={evidence.highlight} alt="" />
          {evidence.patches.map(item => <button className="evidence-pin" type="button" key={item.id}
            aria-label={`Inspect patch ${item.id}`} aria-pressed={item.id === selected} onClick={() => setSelected(item.id)}
            style={{ left: `${item.x_pct}%`, top: `${item.y_pct}%` }}>{item.id}</button>)}
        </figure>
        <ImageSource evidence={evidence.recent} />
      </div>
    </div>
    {patch ? <div className="panel evidence-patch">
      <strong>Patch {patch.id} · {patch.hectares} hectares</strong>
      <p>Plant greenness fell from {patch.earlier_greenness} to {patch.recent_greenness}. Check whether harvest, irrigation, or crop damage could explain the change.</p>
      <p className="support-text">Inspection point · {patch.latitude}, {patch.longitude}</p>
      <label>Choose a patch <select value={selected ?? ''} onChange={event => setSelected(Number(event.target.value))}>
        {evidence.patches.map(item => <option key={item.id} value={item.id}>Patch {item.id} · {item.hectares} hectares</option>)}
      </select></label>
    </div> : <p role="status">{evidence.shared_pct < 20
      ? 'There was too little clear imagery in both periods to flag patches.'
      : 'No crop patches met the inspection threshold for these dates.'}</p>}
    <details className="result-details"><summary>How patches are chosen</summary>
      <p>Usable comparison for {evidence.shared_pct}% of the area at {evidence.grid_m} m sampling. A patch needs at least {evidence.min_cells} connected samples and a greenness drop of {evidence.min_drop} NDVI or more against the median of the prior three years. Each sample requires clear data in at least two prior periods. The map shows up to eight flagged patches and uses Dynamic World to identify cropland. A drop in greenness can have several causes.</p>
    </details>
  </>
}

export function SatelliteEvidence({ profile, mode }: { profile: LandProfile; mode: 'inspection' | 'history' }) {
  const [inspection, setInspection] = useState<InspectionEvidence | null>(null)
  const [history, setHistory] = useState<HistoryEvidence | null>(null)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    const request = new AbortController()
    const task = mode === 'inspection' ? getInspection(profile.id, request.signal).then(setInspection)
      : getHistory(profile.id, request.signal).then(setHistory)
    void task.catch(failure => {
      if (!request.signal.aborted) setError(failure instanceof Error ? failure.message : 'Could not load the satellite images.')
    })
    return () => request.abort()
  }, [mode, profile.id, retry])

  return <section className="panel land-evidence" aria-labelledby={`evidence-${mode}`}>
    <h3 id={`evidence-${mode}`}>{mode === 'inspection' ? 'Where should I check first?' : 'See this land 30 years ago'}</h3>
    {mode === 'inspection' && inspection && <Inspection evidence={inspection} />}
    {mode === 'history' && history && <History history={history} />}
    {error ? <><p className="area-error" role="alert">{error}</p><button className="guide-button" type="button"
      onClick={() => { setError(''); setRetry(value => value + 1) }}>Retry</button></>
      : !inspection && !history && <p role="status">Loading satellite images…</p>}
  </section>
}

type Comparison = { other: LandProfile; first: PlotEvidence; second: PlotEvidence }
function amount(value: number | null, unit: string) { return value === null ? 'No data' : `${value}${unit}` }

export function ComparePlots({ profile, demos, recent }: {
  profile: LandProfile; demos: LandDemo[]; recent: { id: string; title: string }[]
}) {
  const choices = [...demos, ...recent.filter(item => !demos.some(demo => demo.id === item.id))].filter(item => item.id !== profile.id)
  const [choice, setChoice] = useState(choices[0]?.id ?? '')
  const [comparison, setComparison] = useState<Comparison | null>(null)
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const [running, setRunning] = useState('')
  useEffect(() => {
    if (!running) return
    const request = new AbortController()
    void Promise.all([getLandProfile(running, request.signal), getPlotEvidence(profile.id, request.signal),
      getPlotEvidence(running, request.signal)]).then(([other, first, second]) => {
      if (!request.signal.aborted) setComparison({ other, first, second })
    }).catch(failure => {
      if (!request.signal.aborted) setError(failure instanceof Error ? failure.message : 'Could not compare the plots.')
    }).finally(() => {
      if (!request.signal.aborted) { setPending(false); setRunning('') }
    })
    return () => request.abort()
  }, [profile.id, running])

  const secondTitle = choices.find(item => item.id === comparison?.other.id)?.title
  const common = profile.observations.flatMap(first => {
    const second = comparison?.other.observations.find(item => item.start === first.start && item.end === first.end)
    return second ? [[first, second] as const] : []
  })
  const oldest = common[0]
  const newest = common.at(-1)
  return <section className="panel land-evidence" aria-labelledby="compare-plots-heading">
    <h3 id="compare-plots-heading">Compare two plots</h3>
    <p className="support-text">Compare this plot with a demo or a plot you ran earlier. To compare your own plots, draw and analyze both using the same dates.</p>
    <form className="evidence-compare-form" onSubmit={event => {
      event.preventDefault()
      setError('')
      setComparison(null)
      setPending(true)
      setRunning(choice)
    }}>
      <label>Second plot <select value={choice} disabled={pending} onChange={event => setChoice(event.target.value)}>
        {choices.length === 0 && <option value="">Analyze another plot first</option>}
        {choices.map(item => <option value={item.id} key={item.id}>{item.title}</option>)}
      </select></label>
      <button className="primary-button" type="submit" disabled={!choice || pending}>{pending ? 'Comparing…' : 'Compare plots'}</button>
    </form>
    {error && <p className="area-error" role="alert">{error}</p>}
    {comparison && <>
      <p className="support-text">{oldest && newest
        ? `Shared satellite dates · ${oldest[0].start} to ${newest[0].end}`
        : 'The plots have no matching satellite dates for a land-cover comparison.'}</p>
      <div className="land-evidence-pair">{([0, 1] as const).map(index => {
        const plot = index === 0 ? profile : comparison.other
        const facts = index === 0 ? comparison.first : comparison.second
        const snapshot = newest?.[index]
        const earliest = oldest?.[index]
        return <section className="panel evidence-patch" key={plot.id}>
          <h4>Plot {index + 1} · {index === 0 ? plot.title : secondTitle ?? plot.title}</h4>
          {snapshot?.image && <figure className="land-image"><img src={snapshot.image} alt={`Plot ${index + 1} in ${period(snapshot.start)}`} /></figure>}
          <dl className="land-values">
            <div><dt>Plot size</dt><dd>{plot.area_km2} km²</dd></div>
            <div><dt>Average slope</dt><dd>{amount(facts.average_slope_deg, '°')}</dd><dd className="scenario-value-note">{facts.slope_coverage_pct}% of land sampled</dd></div>
            <div><dt>Land where water was seen</dt><dd>{amount(facts.water_area_pct, '%')}</dd><dd className="scenario-value-note">Share of land observed in 1984–2021. Coverage {facts.water_coverage_pct}%.</dd></div>
          </dl>
          {snapshot && earliest && <div className="support-text">
            <p>Crops {amount(earliest.classified_pct ? (earliest.land_cover_pct.Crops ?? 0) : null, '%')} → {amount(snapshot.classified_pct ? (snapshot.land_cover_pct.Crops ?? 0) : null, '%')}</p>
            <p>Built-up land {amount(earliest.classified_pct ? (earliest.land_cover_pct['Built area'] ?? 0) : null, '%')} → {amount(snapshot.classified_pct ? (snapshot.land_cover_pct['Built area'] ?? 0) : null, '%')}</p>
            <p>Land type identified for {earliest.classified_pct}% → {snapshot.classified_pct}% of this plot on the comparison dates.</p>
          </div>}
        </section>
      })}</div>
      <p className="support-text">Historical water includes rivers and ponds. Crop and built-up shares use only land with an identified type. Sources include JRC Global Surface Water, Copernicus elevation, and Dynamic World.</p>
    </>}
  </section>
}
