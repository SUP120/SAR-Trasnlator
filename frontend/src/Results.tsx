import { useEffect, useState } from 'react'
import { Download, Radar, X } from 'lucide-react'
import { apiUrl, getExplanation, type Explanation, type Language, type Rejection, type Result } from './api'

const number = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 2 })
const reasonLabels = {
  missing_before: 'No compatible before observation', missing_after: 'No compatible after observation',
  no_shared_coverage: 'No shared study-area coverage', lower_rank: 'Another group ranked higher',
}

export function PairingDetails({ rejections }: { rejections: Rejection[] }) {
  if (!rejections.length) return null
  return <details className="result-details"><summary>Other orbit groups ({rejections.length})</summary>
    <ul>{rejections.map(({ geometry, platform, reason, footprint_coverage }) =>
      <li key={`${geometry.orbit_pass}-${geometry.relative_orbit}-${geometry.mode}-${geometry.polarizations.join('-')}-${platform}-${reason}`}>
        {geometry.orbit_pass.toLowerCase()} orbit {geometry.relative_orbit}, {geometry.mode}, {geometry.polarizations.join('/')}
        {platform && `, ${platform}`} · {reasonLabels[reason]}
        {footprint_coverage !== null && ` (${number.format(100 * footprint_coverage)}% shared footprint)`}
      </li>)}</ul>
  </details>
}

function ResultExplanation({ id }: { id: string }) {
  const [language, setLanguage] = useState<Language>('en')
  const [text, setText] = useState<Explanation | null>(null)
  const [error, setError] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    getExplanation(id, language, controller.signal).then(setText).catch(() => {
      if (!controller.signal.aborted) setError(true)
    })
    return () => controller.abort()
  }, [id, language, attempt])

  function changeLanguage(next: Language) {
    if (next === language) return
    setText(null)
    setError(false)
    setLanguage(next)
  }

  return <section className="panel result-card" aria-labelledby="explanation-heading">
    <div className="result-card-heading">
      <h3 id="explanation-heading">Explanation</h3>
      <div className="layer-buttons" role="group" aria-label="Explanation language">
        <button type="button" onClick={() => changeLanguage('en')} aria-pressed={language === 'en'}>English</button>
        <button type="button" onClick={() => changeLanguage('hi')} aria-pressed={language === 'hi'} lang="hi">हिन्दी</button>
      </div>
    </div>
    {text ? <div className="explanation" lang={text.language} aria-live="polite">
      <h4>{text.headline}</h4><p>{text.summary}</p>
      <ul>{text.limitations.map((item) => <li key={item}>{item}</li>)}</ul><p className="verify-text">{text.verification}</p>
    </div> : error ? <div className="explanation"><p role="alert">The explanation could not load.</p>
      <button className="guide-button" type="button" onClick={() => { setError(false); setAttempt(attempt + 1) }}>Try again</button></div>
      : <p className="support-text" role="status">Loading explanation…</p>}
    <a className="report-button" href={apiUrl(`analyses/${id}/report.pdf?lang=${language}`)} download>
      <Download size={17} /> Download {language === 'en' ? 'English' : 'Hindi'} PDF
    </a>
  </section>
}

export function FloodSummary({ result, onClose }: { result: Result; onClose: () => void }) {
  const { stats, quality, cached_event } = result
  const classifications = {
    possible_flooding: 'Possible surface-water expansion', no_change_detected: 'No qualifying change detected',
    insufficient_data: 'Insufficient overlapping data',
  }
  const hasCoverage = stats.valid_coverage_pct > 0
  return <section className="panel flood-summary" aria-labelledby="flood-summary-heading">
    <div className="flood-summary-title">
      <p className="support-text">{result.source === 'synthetic' ? 'Practice example · invented observations' : result.title}</p>
      <h2 id="flood-summary-heading">{classifications[result.classification]}</h2>
    </div>
    <div className="flood-summary-actions">
      <a className="report-button" href="#results-heading">Compare images</a>
      <button className="guide-button" type="button" onClick={onClose}><X size={16} /> Clear result</button>
      {cached_event && <a className="support-text" href={cached_event.reference_url} target="_blank" rel="noreferrer">Published comparison map</a>}
    </div>
    <div className="flood-stat-cards">
      {hasCoverage && <div className="flood-share flood-stat-water">
      <span>Possible water expansion</span>
      <strong>{number.format(stats.flood_ha)} ha</strong>
      <span>{stats.flood_pct_of_aoi > 0 && stats.flood_pct_of_aoi < .01 ? '<0.01' : number.format(stats.flood_pct_of_aoi)}% of the sampled study area</span>
      <meter min={0} max={100} value={stats.flood_pct_of_aoi} aria-label="Sampled study area with detected water change" />
      </div>}
      <div className="flood-share flood-stat-coverage">
        <span>Shared radar coverage</span><strong>{number.format(stats.valid_coverage_pct)}%</strong>
        <span>Valid in both periods</span>
        <meter min={0} max={100} value={stats.valid_coverage_pct} aria-label="Shared valid radar coverage" />
      </div>
      <div className="flood-share flood-stat-quality">
        <span>Observation quality</span>
        <span className={`quality-pill ${quality.overall.toLowerCase()}`}>{quality.overall}</span>
        <a href="#quality-heading">See quality factors</a>
      </div>
    </div>
  </section>
}

export function Results({ result, rejections }: { result: Result; rejections: Rejection[] }) {
  const { stats, quality, parameters, geometry } = result
  const metrics = [
    ['Detected water change', stats.valid_coverage_pct ? `${number.format(stats.flood_ha)} ha` : 'Unavailable',
      stats.valid_coverage_pct ? `${number.format(stats.flood_km2)} km² · ${number.format(stats.flood_pct_of_aoi)}% of sampled area` : 'No common coverage'],
    ['Study area', `${number.format(result.aoi_area_km2)} km²`, `${number.format(stats.sampled_aoi_km2)} km² sampled`],
    ['Shared valid coverage', `${number.format(stats.valid_coverage_pct)}%`, 'Valid in both periods'],
    ['Pre-existing water', `${number.format(stats.preexisting_water_ha)} ha`, 'Excluded from change detection'],
  ]

  return <section className="results" aria-labelledby="results-heading">
    <h2 id="results-heading">Before, after and detected change</h2>
    <div className="flood-images">
      {([['before', 'Before'], ['after', 'After'], ['change', 'Detected change']] as const).map(([layer, label]) => <figure className={`panel flood-image-${layer}`} key={layer}>
        <img src={apiUrl(result.layers[layer])} alt={`${label} radar composite for the study area`} loading="lazy" />
        <figcaption>{layer === 'change' && <i className="legend-change" aria-hidden="true" />}{label}
          <span>{layer === 'change' ? 'Teal shows possible surface-water expansion' : [...new Set(result[layer === 'before' ? 'pre' : 'post'].map(scene => scene.acquired_at.slice(0, 10)))].join(', ')}</span>
        </figcaption>
      </figure>)}
    </div>
    <div className="flood-report-link"><a className="report-button" href={apiUrl(`analyses/${result.id}/report.pdf?lang=en`)} download><Download size={16} /> Download report</a></div>
    <details className="panel evidence-details">
      <summary>Measurements, observation quality and method</summary>
    <dl className="metrics">{metrics.map(([label, value, note]) => <div className="panel metric" key={label}>
      <dt>{label}</dt><dd>{value}</dd><dd className="metric-note">{note}</dd>
    </div>)}</dl>
    <div className="result-grid">
      <section className="panel result-card" aria-labelledby="observations-heading">
        <h3 id="observations-heading"><Radar size={17} /> Observation dates</h3>
        <p className="support-text">{geometry.orbit_pass.toLowerCase()} orbit {geometry.relative_orbit} · {geometry.mode} · {[...geometry.polarizations].reverse().join('/')}</p>
        <div className="observation-grid">
          {([['Before', result.pre], ['After', result.post]] as const).map(([key, scenes]) => <div key={key}>
            <h4>{key}</h4><ul>{scenes.map((scene) => <li key={scene.id}><time dateTime={scene.acquired_at}>{scene.acquired_at.slice(0, 10)}</time><span>{scene.platform}</span></li>)}</ul>
          </div>)}
        </div>
        <p className="support-text">Event date <time dateTime={result.periods.event}>{result.periods.event}</time> · all dates UTC</p>
        <PairingDetails rejections={rejections} />
      </section>
      <section className="panel result-card" aria-labelledby="quality-heading">
        <div className="result-card-heading"><h3 id="quality-heading">Observation quality</h3><span className={`quality-pill ${quality.overall.toLowerCase()}`}>{quality.overall}</span></div>
        <table className="quality-table"><thead><tr><th scope="col">Factor</th><th scope="col">Observed</th><th scope="col">Rating</th></tr></thead>
          <tbody>{quality.factors.map((factor) => <tr key={factor.name}><th scope="row">{factor.name}</th><td>{factor.observed}</td><td>{factor.grade}</td></tr>)}</tbody>
        </table>
      </section>
      <ResultExplanation id={result.id} />
      <section className="panel result-card" aria-labelledby="method-heading">
        <h3 id="method-heading">Method and limitations</h3>
        <p className="support-text">Median VV imagery at {parameters.scale_m} m, with a {parameters.speckle_radius_m} m median filter. The later return must be below {parameters.water_db} dB and the change below {parameters.change_db} dB.</p>
        <dl className="mask-list">
          <div><dt>Pre-existing water</dt><dd>{number.format(result.masks_excluded_ha.preexisting_water)} ha</dd></div>
          <div><dt>Steep or elevated terrain</dt><dd>{number.format(result.masks_excluded_ha.terrain)} ha</dd></div>
          <div><dt>Groups under {parameters.min_cluster_pixels} pixels</dt><dd>{number.format(result.masks_excluded_ha.small_clusters)} ha</dd></div>
        </dl>
        <p className="support-text">Amounts show candidate change removed at each step.</p>
        <ul className="warnings">{result.warnings.map((item) => <li key={item}>{item}</li>)}</ul>
      </section>
    </div>
    <footer className="result-credit">{result.attributions.join(' ')}</footer>
    </details>
  </section>
}
