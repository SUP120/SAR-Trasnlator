import { useEffect, useMemo, useRef, useState, type PointerEvent } from 'react'
import { Minus, Mountain, Plus, RotateCcw, RotateCw } from 'lucide-react'
import { getTerrain, type TerrainGrid, type TerrainStorage } from './landApi'

type Point = { x: number; y: number; height: number; row: number; col: number }
type Face = [Point, Point, Point]
type Camera = { yaw: number; pitch: number; zoom: number; exaggeration: number }

function makeSurface(grid: TerrainGrid) {
  const height = grid.elevations_m.length, width = grid.elevations_m[0].length
  const elevations = grid.elevations_m.flat().filter((value): value is number => value !== null)
  const low = Math.min(...elevations), high = Math.max(...elevations)
  const points = grid.elevations_m.map((row, y) => row.map((value, x): Point | null => value === null ? null : ({
    x: x - (width - 1) / 2, y: y - (height - 1) / 2, height: value, row: y, col: x,
  })))
  const faces: Face[] = []
  for (let y = 0; y < height - 1; y++) {
    for (let x = 0; x < width - 1; x++) {
      const [a, b] = [points[y][x], points[y][x + 1]]
      const [c, d] = [points[y + 1][x], points[y + 1][x + 1]]
      if (a && b && d) faces.push([a, b, d])
      if (a && d && c) faces.push([a, d, c])
    }
  }
  const span = Math.max(width, height) * grid.cell_m
  return { faces, low, high, span, cell: grid.cell_m, width, height }
}

function paint(canvas: HTMLCanvasElement, surface: ReturnType<typeof makeSurface>, camera: Camera, storage?: TerrainStorage) {
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const ratio = Math.min(window.devicePixelRatio || 1, 2)
  const width = canvas.clientWidth, height = canvas.clientHeight
  if (!width || !height) return
  canvas.width = width * ratio
  canvas.height = height * ratio
  ctx.scale(ratio, ratio)

  const angleX = Math.cos(camera.yaw), angleY = Math.sin(camera.yaw)
  const tiltX = Math.cos(camera.pitch), tiltY = Math.sin(camera.pitch)
  const radius = Math.hypot(surface.height, surface.width)
  const relief = (surface.high - surface.low) * camera.exaggeration / surface.cell
  const scale = Math.min(width / (radius * 1.12), height / (radius * tiltX + relief * tiltY + 5)) * camera.zoom
  const centerY = height / 2 + Math.min(relief * tiltY * scale / 2, height / 3)
  const range = Math.max(surface.high - surface.low, 0.1)

  function project(point: Point) {
    const horizontal = point.x * angleX - point.y * angleY
    const depth = point.x * angleY + point.y * angleX
    const z = (point.height - surface.low) * camera.exaggeration / surface.cell
    return { x: width / 2 + horizontal * scale, y: centerY + (depth * tiltX - z * tiltY) * scale, depth: depth * tiltY + z * tiltX }
  }

  const triangles = surface.faces.map(face => {
    const points = face.map(project)
    const elevation = face.reduce((sum, point) => sum + point.height, 0) / 3
    const level = (elevation - surface.low) / range
    const shade = Math.max(-9, Math.min(9, (face[0].height - face[2].height) * 2.2 * camera.exaggeration / 10))
    let color = `hsl(${172 - level * 135} 38% ${31 + level * 37 + shade}%)`
    if (storage) {
      const [a, b, c] = face.map(point => storage[point.row]?.[point.col] ?? null)
      // Gray preserves gaps where the water-balance model has no coverage.
      if (a === null || b === null || c === null) color = '#aab5bc'
      else {
        const fraction = (a + b + c) / 300
        const channels = [237 - 189 * fraction, 152 + 12 * fraction, 72 + 135 * fraction]
        color = `rgb(${channels.map(channel => Math.round(channel)).join(',')})`
      }
    }
    return { points, depth: points.reduce((sum, point) => sum + point.depth, 0), color }
  }).sort((a, b) => a.depth - b.depth)

  for (const { points, color } of triangles) {
    ctx.beginPath()
    ctx.moveTo(points[0].x, points[0].y)
    ctx.lineTo(points[1].x, points[1].y)
    ctx.lineTo(points[2].x, points[2].y)
    ctx.closePath()
    ctx.fillStyle = color
    ctx.strokeStyle = color
    ctx.lineWidth = 0.65
    ctx.fill()
    ctx.stroke()
  }
}

function TerrainModel({ grid, storage, day }: { grid: TerrainGrid; storage?: TerrainStorage; day?: number }) {
  const surface = useMemo(() => makeSurface(grid), [grid])
  const baseline = useMemo(() => ({ yaw: -0.7, pitch: 0.67, zoom: 1,
    exaggeration: Math.min(60, Math.max(1, Math.round(surface.span * 0.24 / Math.max(surface.high - surface.low, 1)))) }), [surface])
  const [camera, setCamera] = useState<Camera>(baseline)
  const canvas = useRef<HTMLCanvasElement>(null)
  const pointer = useRef<{ id: number; x: number; y: number } | null>(null)

  useEffect(() => {
    const element = canvas.current
    if (!element || !surface.faces.length) return
    const render = () => paint(element, surface, camera, storage)
    render()
    const observer = new ResizeObserver(render)
    observer.observe(element)
    return () => observer.disconnect()
  }, [surface, camera, storage])

  function drag(event: PointerEvent<HTMLCanvasElement>) {
    const location = pointer.current
    if (!location || location.id !== event.pointerId) return
    const dx = event.clientX - location.x, dy = event.clientY - location.y
    pointer.current = { id: event.pointerId, x: event.clientX, y: event.clientY }
    setCamera(value => ({ ...value, yaw: value.yaw + dx * .012, pitch: Math.min(1.35, Math.max(.25, value.pitch + dy * .008)) }))
  }

  function rotate(amount: number) { setCamera(value => ({ ...value, yaw: value.yaw + amount })) }
  function zoom(multiplier: number) { setCamera(value => ({ ...value, zoom: Math.min(2.5, Math.max(.65, value.zoom * multiplier)) })) }

  if (!surface.faces.length) return <p className="support-text">There aren’t enough nearby height measurements to draw this area in 3D.</p>
  return <>
    <div className="terrain-reading">
      <p>{storage
        ? 'The shape shows the high and low parts of the land. Colors show how much water the soil might hold on this day.'
        : 'This map shows which parts of your selected area are higher or lower. The colors help you see small changes in height.'}</p>
      {storage ? <div className="terrain-key" aria-label="Colors for estimated water in the soil">
        <div className="terrain-height-key terrain-storage-key"><span>Orange · Less water</span><i aria-hidden="true" /><span>Blue · More water</span></div>
        <span className="terrain-no-data"><i aria-hidden="true" />Gray · No estimate</span>
      </div> : <div className="terrain-key" aria-label="Colors for land height">
        <div className="terrain-height-key"><span>Teal · Lower · {surface.low.toFixed(1)} m</span><i aria-hidden="true" /><span>Tan · Higher · {surface.high.toFixed(1)} m</span></div>
        <span>{(surface.high - surface.low).toFixed(1)} m from lowest to highest</span>
      </div>}
    </div>
    <p className="support-text terrain-instructions">Drag to look from another angle. Use + or − to zoom.</p>
    <div className="terrain-stage">
      <canvas ref={canvas} role="img" aria-label={storage ? `3D map of estimated soil water on day ${day}` : '3D map showing the height of the selected land'}
        onPointerDown={event => {
          if (!event.isPrimary || event.button !== 0) return
          event.currentTarget.setPointerCapture(event.pointerId)
          pointer.current = { id: event.pointerId, x: event.clientX, y: event.clientY }
        }} onPointerMove={drag} onLostPointerCapture={() => { pointer.current = null }} />
      <div className="layer-buttons terrain-controls" role="group" aria-label="Terrain view controls">
        <button type="button" aria-label="Rotate left" title="Rotate left" onClick={() => rotate(-0.35)}><RotateCcw size={16} /></button>
        <button type="button" aria-label="Rotate right" title="Rotate right" onClick={() => rotate(0.35)}><RotateCw size={16} /></button>
        <button type="button" aria-label="Zoom in terrain" title="Zoom in" onClick={() => zoom(1.2)}><Plus size={16} /></button>
        <button type="button" aria-label="Zoom out terrain" title="Zoom out" onClick={() => zoom(1 / 1.2)}><Minus size={16} /></button>
        <button type="button" onClick={() => setCamera(baseline)}>Reset</button>
      </div>
    </div>
    <div className="terrain-settings">
      <label>Make height differences stand out <strong>{camera.exaggeration}×</strong>
        <input type="range" min={1} max={60} value={camera.exaggeration}
          onChange={event => setCamera(value => ({ ...value, exaggeration: Number(event.target.value) }))} />
      </label>
      <p className="support-text">The view stretches height differences so they’re easier to see. Set it to 1× to see the shape without stretching.</p>
    </div>
    <details className="result-details">
      <summary>How the map was made</summary>
      <p className="support-text">The map uses height measurements about {grid.cell_m} m apart. Heights are measured from a standard sea-level reference (EGM2008) and can include treetops and rooftops.</p>
      {storage && <p className="support-text">The color scale goes from 0% of what the soil can hold (orange) to 100% (blue). The estimate uses the rain and soil settings for this run. The land shape stays the same as you move through the days.</p>}
    </details>
  </>
}

export function TerrainView({ id, storage, day }: { id: string; storage?: TerrainStorage; day?: number }) {
  const [grid, setGrid] = useState<TerrainGrid | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const request = new AbortController()
    getTerrain(id, request.signal).then(setGrid).catch(problem => {
      if (!request.signal.aborted) setError(problem instanceof Error ? problem.message : 'Could not load elevation data.')
    })
    return () => request.abort()
  }, [id, attempt])
  const aligned = !storage || !grid || (storage.length === grid.elevations_m.length &&
    storage.every(row => row.length === grid.elevations_m[0].length))
  const headingId = storage ? 'scenario-terrain-heading' : 'terrain-heading'
  return <section className="panel land-terrain" aria-labelledby={headingId}>
    <div className="land-subheading"><Mountain size={21} /><h3 id={headingId}>{storage ? `Estimated soil water in 3D · Day ${day}` : '3D terrain'}</h3></div>
    {grid && !aligned ? <p className="area-error" role="alert">The soil water map couldn’t be lined up with the 3D terrain. You can still use the 2D map.</p>
      : grid ? <><TerrainModel grid={grid} storage={storage} day={day} />
      <p className="result-credit"><a href="https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_DEM_GLO30_2024_1">Copernicus DEM GLO-30</a> · {grid.credit}</p></>
      : error ? <><p className="area-error" role="alert">{error}</p><button type="button" className="guide-button" onClick={() => { setError(''); setAttempt(value => value + 1) }}>Retry terrain</button></>
        : <p className="support-text" role="status">Loading land heights…</p>}
  </section>
}
