import { useEffect, useState } from 'react'
import type { FeatureCollection, Polygon as Geometry } from 'geojson'
import { divIcon, DomEvent, latLngBounds, type LatLng, type LatLngTuple } from 'leaflet'
import { Check, Crosshair, Minus, MousePointer2, Plus, Scan, Spline, X } from 'lucide-react'
import { GeoJSON, ImageOverlay, MapContainer, Marker, Pane, Polygon, Polyline, ScaleControl, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import { apiUrl, type Layer, type Result } from './api'
import { initialView, type Location } from './locations'

type Tool = 'rectangle' | 'polygon'
type BasemapMode = 'satellite' | 'terrain'
type Place = { name: string; lat: number; lon: number; rank: number }
type Basemap = { countries: FeatureCollection; boundaries: FeatureCollection; rivers: FeatureCollection; places: Place[] }

const bounds: [LatLngTuple, LatLngTuple] = [[7, 65], [36, 102]]
const areaStyle = { color: '#135e99', weight: 3, fillColor: '#5caee4', fillOpacity: 0.24, interactive: false }
const drawStyle = { ...areaStyle, dashArray: '6 4' }
const assetBase = import.meta.env.BASE_URL
const customTileUrl = import.meta.env.VITE_BASEMAP_URL
const customTileCredit = import.meta.env.VITE_BASEMAP_ATTRIBUTION
const useCustomTiles = !!(customTileUrl && customTileCredit)
const satelliteUrl = useCustomTiles ? customTileUrl : 'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg'
const customNativeZoom = Number(import.meta.env.VITE_BASEMAP_MAX_NATIVE_ZOOM ?? 18)
const nativeZoom = useCustomTiles && Number.isInteger(customNativeZoom) && customNativeZoom >= 6 && customNativeZoom <= 18 ? customNativeZoom : 14

function rectangle(corner: LatLng, opposite: LatLng): LatLngTuple[] {
  return [[corner.lat, corner.lng], [corner.lat, opposite.lng], [opposite.lat, opposite.lng], [opposite.lat, corner.lng]]
}

function PlaceLabel({ place }: { place: Place }) {
  const label = document.createElement('span')
  label.textContent = place.name
  const icon = divIcon({ className: 'place-label', html: label, iconSize: [0, 0], iconAnchor: [0, 0] })
  return <Marker position={[place.lat, place.lon]} icon={icon} interactive={false} keyboard={false} />
}

function ReferenceLayers({ data, view, mode, onTilesMissing }: {
  data: Basemap | null; view: number; mode: BasemapMode; onTilesMissing: (missing: boolean) => void
}) {
  const map = useMap()
  const places: Place[] = []
  const pixels: { x: number; y: number }[] = []
  const extent = map.getBounds().pad(0.1)
  for (const place of data?.places ?? []) {
    if (!extent.contains([place.lat, place.lon]) || place.rank > view) continue
    const point = map.project([place.lat, place.lon], view)
    if (pixels.some((other) => Math.abs(other.x - point.x) < 96 && Math.abs(other.y - point.y) < 26)) continue
    places.push(place)
    pixels.push(point)
  }

  return <>
    <Pane name="terrain-reference" style={{ zIndex: 190 }}>
      <ImageOverlay url={`${assetBase}south-asia-relief.webp`} bounds={bounds} alt="Natural Earth regional terrain" />
    </Pane>
    {data && <>
      <GeoJSON data={data.countries} interactive={false} style={{ color: '#6e8499', opacity: 0.65, weight: 1, fill: false }} />
      <GeoJSON data={data.boundaries} interactive={false} style={{ color: '#587087', opacity: 0.65, weight: 1, dashArray: '4 4' }} />
      {mode === 'terrain' && <GeoJSON data={data.rivers} interactive={false} style={{ color: '#5892bc', opacity: 0.74, weight: 1.15 }} />}
      {places.map((place) => <PlaceLabel key={`${place.lat},${place.lon}`} place={place} />)}
    </>}
    {mode === 'satellite' && <TileLayer url={satelliteUrl} minZoom={6} maxZoom={18} maxNativeZoom={nativeZoom}
      bounds={bounds} noWrap eventHandlers={{
        loading: () => onTilesMissing(false),
        tileerror: () => onTilesMissing(true),
      }} />}
  </>
}

function coordinates({ lat, lng }: LatLng) {
  return `${Math.abs(lat).toFixed(3)}° ${lat < 0 ? 'S' : 'N'}, ${Math.abs(lng).toFixed(3)}° ${lng < 0 ? 'W' : 'E'}`
}

function isolateControl(element: HTMLDivElement | null) {
  if (element) DomEvent.disableClickPropagation(element)
}

type MapProps = {
  location: Location
  locationRevision: number
  geometry: Geometry | null
  areaValidated: boolean
  result: Result | null
  onGeometry: (geometry: Geometry) => void
}

function MapContents({ location, locationRevision, geometry, areaValidated, result, onGeometry, layer, opacity, mode, onTilesMissing }: MapProps & {
  layer: Layer; opacity: number; mode: BasemapMode; onTilesMissing: (missing: boolean) => void
}) {
  const map = useMap()
  const [tool, setTool] = useState<Tool | null>(null)
  const [points, setPoints] = useState<LatLng[]>([])
  const [cursor, setCursor] = useState<LatLng | null>(null)
  const [view, setView] = useState({ center: map.getCenter(), zoom: map.getZoom() })
  const [data, setData] = useState<Basemap | null>(null)
  const [basemapIssue, setBasemapIssue] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    fetch(`${assetBase}south-asia.json`, { signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error('Map data unavailable')
        return response.json() as Promise<Basemap>
      })
      .then(setData)
      .catch(() => { if (!controller.signal.aborted) setBasemapIssue(true) })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    const container = map.getContainer()
    container.setAttribute('aria-label', 'Study area map')
    container.setAttribute('aria-describedby', 'drawing-guide')
    const observer = new ResizeObserver(() => map.invalidateSize({ pan: false }))
    observer.observe(container)
    return () => observer.disconnect()
  }, [map])

  useEffect(() => {
    map.setView(location.center, location.zoom, { animate: false })
  }, [location, locationRevision, map])

  useEffect(() => {
    if (result) map.fitBounds(result.bounds, { animate: false, maxZoom: 14, padding: [38, 56] })
  }, [result, map])

  useEffect(() => {
    map.getContainer().classList.toggle('is-drawing', tool !== null)
    if (tool) map.doubleClickZoom.disable()
    else map.doubleClickZoom.enable()
  }, [map, tool])

  function stopDrawing() {
    setTool(null)
    setPoints([])
    setCursor(null)
  }

  function finish(vertices: LatLngTuple[]) {
    const ring = vertices.map(([lat, lon]) => [lon, lat])
    onGeometry({ type: 'Polygon', coordinates: [[...ring, ring[0]]] })
    stopDrawing()
  }

  function addPoint(point: LatLng) {
    if (!tool || !latLngBounds(bounds).contains(point)) return
    if (points.at(-1)?.distanceTo(point) === 0) return
    if (tool === 'rectangle' && points.length === 1) {
      if (point.lat !== points[0].lat && point.lng !== points[0].lng) finish(rectangle(points[0], point))
    } else if (points.length < 500) {
      setPoints([...points, point])
    }
  }

  function chooseTool(nextTool: Tool) {
    stopDrawing()
    if (tool !== nextTool) {
      setTool(nextTool)
      map.getContainer().focus({ preventScroll: true })
    }
  }

  useMapEvents({
    moveend: () => setView({ center: map.getCenter(), zoom: map.getZoom() }),
    click: ({ latlng }) => addPoint(latlng),
    mousemove: ({ latlng }) => { if (tool === 'rectangle' && points.length) setCursor(latlng) },
    keydown: ({ originalEvent }) => {
      if (!tool || originalEvent.target !== map.getContainer()) return
      if (originalEvent.key === 'Escape') stopDrawing()
      if (originalEvent.key === 'Enter') {
        originalEvent.preventDefault()
        if (originalEvent.shiftKey && tool === 'polygon' && points.length >= 3) {
          finish(points.map(({ lat, lng }) => [lat, lng]))
        } else if (!originalEvent.shiftKey) {
          addPoint(map.getCenter())
        }
      }
    },
  })

  let hint = 'Zoom in and draw a boundary around your study area.'
  if (geometry) hint = areaValidated ? 'Study boundary validated.' : 'Validate your boundary in Analysis setup.'
  if (result) hint = result.source === 'synthetic' ? 'Synthetic data for practice' : 'Sentinel-1 comparison'
  if (result?.cached_event) hint = 'Cached Sentinel-1 comparison'
  if (tool === 'rectangle') hint = points.length ? 'Place the opposite corner.' : 'Place the first corner.'
  if (tool === 'polygon') hint = 'Place at least three vertices, then finish the polygon.'

  const boundary = result?.aoi ?? geometry
  return <>
    <ReferenceLayers data={data} view={view.zoom} mode={mode} onTilesMissing={onTilesMissing} />
    <ScaleControl imperial={false} position="bottomleft" />
    {result && <Pane name="analysis-image" style={{ zIndex: 420 }}>
      <ImageOverlay key={layer} url={apiUrl(result.layers[layer])} bounds={result.bounds} opacity={opacity}
        alt={`${layer} comparison layer`} />
    </Pane>}
    <Pane name="study-boundary" style={{ zIndex: 440 }}>
      {boundary && <Polygon positions={boundary.coordinates.map((ring) => ring.map(([lon, lat]): LatLngTuple => [lat, lon]))}
        pathOptions={result ? { ...areaStyle, fillOpacity: 0 } : areaStyle} />}
      {tool === 'rectangle' && points[0] && cursor && <Polygon positions={rectangle(points[0], cursor)} pathOptions={drawStyle} />}
      {tool === 'polygon' && points.length > 0 && <Polyline positions={points} pathOptions={drawStyle} />}
    </Pane>

    <div className="map-tools" ref={isolateControl} role="group" aria-label="Area drawing tools">
      <button type="button" title="Pan map" aria-label="Pan map" aria-pressed={tool === null} onClick={stopDrawing}><MousePointer2 size={17} /></button>
      <button type="button" title="Draw rectangle" aria-label="Draw rectangle" aria-pressed={tool === 'rectangle'} onClick={() => chooseTool('rectangle')}><Scan size={18} /></button>
      <button type="button" title="Draw polygon" aria-label="Draw polygon" aria-pressed={tool === 'polygon'} onClick={() => chooseTool('polygon')}><Spline size={18} /></button>
    </div>
    <div className="map-navigation" ref={isolateControl} role="group" aria-label="Map navigation">
      <button type="button" title="Zoom in" aria-label="Zoom in" disabled={view.zoom >= map.getMaxZoom()} onClick={() => map.zoomIn()}><Plus size={19} /></button>
      <button type="button" title="Zoom out" aria-label="Zoom out" disabled={view.zoom <= map.getMinZoom()} onClick={() => map.zoomOut()}><Minus size={19} /></button>
      <button type="button" title="Recenter map" aria-label="Recenter map" onClick={() => {
        if (result) map.fitBounds(result.bounds, { maxZoom: 14, padding: [38, 56] })
        else map.setView(location.center, location.zoom)
      }}><Crosshair size={17} /></button>
    </div>
    {tool && <div className="drawing-target" aria-hidden="true"><Crosshair size={20} /></div>}
    <div className="map-hint" ref={isolateControl} role="status">
      <span>{basemapIssue ? 'Map reference labels are unavailable.' : hint}</span>
      {tool === 'polygon' && points.length >= 3 && <button type="button" onClick={() => finish(points.map(({ lat, lng }) => [lat, lng]))}><Check size={15} /> Finish polygon</button>}
      {tool && <button type="button" title="Cancel drawing" aria-label="Cancel drawing" onClick={stopDrawing}><X size={16} /></button>}
    </div>
    <div className="map-coordinates" aria-hidden="true">{coordinates(view.center)}</div>
  </>
}

export function StudyMap(props: MapProps) {
  const [layer, setLayer] = useState<Layer>('change')
  const [opacity, setOpacity] = useState(0.75)
  const [mode, setMode] = useState<BasemapMode>('satellite')
  const [tilesMissing, setTilesMissing] = useState(false)
  useEffect(() => { setLayer('change'); setOpacity(0.75) }, [props.result?.id])
  return <section className="panel map-panel" aria-labelledby="map-heading">
    <div className="map-heading">
      <div>
        <h2 id="map-heading">Study area map</h2>
        <p>{props.result ? props.result.title : <>{props.location.name} <span aria-hidden="true">·</span> {props.location.region}</>}</p>
      </div>
      <div className="layer-buttons map-basemap" role="group" aria-label="Basemap">
        <button type="button" aria-pressed={mode === 'satellite'} onClick={() => setMode('satellite')}>Satellite</button>
        <button type="button" aria-pressed={mode === 'terrain'} onClick={() => { setMode('terrain'); setTilesMissing(false) }}>Terrain</button>
      </div>
    </div>
    <MapContainer center={initialView.center} zoom={initialView.zoom} minZoom={6} maxZoom={18}
      maxBounds={bounds} maxBoundsViscosity={1} preferCanvas zoomControl={false} attributionControl={false}>
      <MapContents {...props} layer={layer} opacity={opacity} mode={mode} onTilesMissing={setTilesMissing} />
    </MapContainer>
    {mode === 'satellite' && tilesMissing && <p className="map-tile-status" role="status">Terrain fills gaps where satellite tiles are unavailable.</p>}
    {props.result && <div className="map-layer-bar">
      <div className="layer-buttons" role="group" aria-label="Comparison layer">
        {(['before', 'after', 'change'] as const).map((option) => <button key={option} type="button" aria-pressed={layer === option}
          onClick={() => setLayer(option)}>{option === 'change' ? 'Detected change' : option === 'before' ? 'Before' : 'After'}</button>)}
      </div>
      <label className="layer-opacity">Overlay opacity<input type="range" min={0} max={1} step={0.01} value={opacity}
        onChange={(event) => setOpacity(Number(event.target.value))} /></label>
    </div>}
    <div className="map-footer">
      <div className="legend"><span><i className="legend-area" /> Study area</span>
        {props.result && layer === 'change' ? <span><i className="legend-change" /> Detected water change</span> : mode === 'terrain' && <span><i className="legend-river" /> River</span>}
      </div>
      <div className="credit">
        <a href="https://www.naturalearthdata.com/about/terms-of-use/" target="_blank" rel="noreferrer">Natural Earth</a>
        {mode === 'satellite' && <span> · {useCustomTiles ? customTileCredit : <>
          <a href="https://cloudless.eox.at/" target="_blank" rel="noreferrer">EOxCloudless</a> by EOX IT Services GmbH (contains modified Copernicus Sentinel data 2016)
        </>}</span>}
        <span> · </span><a href="https://leafletjs.com/" target="_blank" rel="noreferrer">Leaflet</a>
      </div>
    </div>
  </section>
}
