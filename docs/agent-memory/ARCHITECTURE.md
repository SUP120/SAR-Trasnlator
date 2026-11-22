# Architecture

| Path | Purpose |
| --- | --- |
| `backend/app/main.py` | FastAPI composition, health/config metadata, and AOI validation route |
| `backend/app/config.py` | Default and environment-based AOI cap, explicit CORS origins, Earth Engine project presence |
| `backend/app/aoi.py` | GeoJSON Polygon input validation, geometry checks with Shapely, WGS84 ellipsoidal area with pyproj |
| `backend/app/api/analyses.py`, `backend/app/jobs.py` | Asynchronous submissions, in-memory status and layers, reporting endpoints, bounded work queue |
| `backend/app/cached_events.py`, `data/demo_events/` | Versioned historical bundles, stable result IDs, and locally served rasters |
| `backend/app/analysis.py` | Provider orchestration, result schema and provenance |
| `backend/app/pipeline/` | UTC window resolution, orbit pairing, detection and raster rendering, quality rubric |
| `backend/app/providers/` | Shared scene and pixel interface, deterministic synthetic example, optional Earth Engine adapter |
| `backend/app/explanations.py`, `backend/app/reports/` | Grounded bilingual templates and one-page ReportLab export with an embedded Hindi font |
| `backend/tests/` | AOI, pipeline, job, raster, and report tests |
| `frontend/src/App.tsx` | Study area and time-window state, offline example search, validation feedback |
| `frontend/src/StudyMap.tsx` | Leaflet satellite and terrain layers, reference labels, drawing, map navigation |
| `frontend/src/api.ts` | Typed health and validation requests |
| `frontend/src/useAnalysis.ts`, `frontend/src/Results.tsx` | Job polling, statistics, observations, quality, bilingual explanation and export |
| `frontend/src/locations.ts` | Example location list and initial map view |
| `frontend/public/south-asia.json`, `south-asia-relief.webp` | Derived Natural Earth offline regional assets |
| `scripts/build_basemap.py` | Repeatable vector and raster asset preprocessing |
| `scripts/check_access.py` | Optional credentialed Sentinel-1 and auxiliary dataset metadata probe |
| `validation/balasore.py` | Replays the archived radar result and computes shared-footprint agreement with a local JAXA reference |
| `backend/app/api/land.py`, `backend/app/land.py` | Land endpoints, typed profiles, bounded memory for live results, image offset correlation, and scenario rendering |
| `backend/app/providers/land_optical.py` | Earth Engine Sentinel-2, Dynamic World, and regional SMAP monthly observations |
| `backend/app/land_narrative.py`, `backend/app/reports/land_pdf.py` | Optional live AI narrative, cached narratives, template fallback, and measured PDF |
| `backend/app/land_guidance.py` | Typed role and purpose, measured findings, and suggested checks for the land overview |
| `frontend/src/LandWorkspace.tsx` | Timeline, land demo picker, scenario playback, and report download |
| `data/land_demos/`, `scripts/cache_land_demos.py` | Offline profiles and compact land-cover grids rebuilt from archived Earth Engine observations |

`GET /api/health` reports liveness, the max AOI, and whether live submission is configured. Live requests authenticate on demand. `POST /api/aois/validate` accepts a GeoJSON Polygon and returns `area_km2` and `max_area_km2`. Invalid geometry or an exceeded cap returns `422`.

Vite proxies `/api` on localhost. `POST /api/analyses` accepts either a synthetic request or an Earth Engine request with a polygon and window. It returns a job ID and queued status. `GET /api/analyses/{id}` returns the status and result or a comparable-pair diagnostic. Finished results carry three PNG URLs under `/api/analyses/{id}/layers/`, bounds in Leaflet order, and links built by the frontend for `POST .../explain?lang=` and `GET .../report.pdf?lang=`. `/api/demo/events` lists synthetic and historical examples. `/api/demo/events/{slug}` returns a completed historical snapshot with the original Earth Engine provenance and an explicit `cached_event` value.

Leaflet requests satellite tiles from EOX or the configured provider in the browser. The locally served Natural Earth relief sits beneath that layer and remains visible if tiles fail. Radar images and the AOI boundary use higher panes. Basemap choice and radar overlay opacity are independent of analysis jobs. The validation command runs separately from the API and uses the same radar computation and grid as the original result.

`/api/land/catalog` lists the two offline studies and the optional AI capability. `/api/land/analyses` creates a land profile for a validated polygon and monthly window. A profile can serve the scenario, AI summary, and PDF routes under `/api/land/analyses/{id}`. The route allows two live land computations at a time and keeps the 12 most recently used live profiles in memory. Packaged land profiles are loaded from disk. The bounded land store is separate from the raster job queue, with no new database or service. Scenario results are computed on demand from the last eligible classified grid.

`POST /api/land/analyses/{id}/guidance` takes a role and purpose. It returns measured evidence and purpose-specific checks. When requested and configured, it can also provide a separate AI narrative. Successful AI responses are cached by analysis ID, role and purpose, with a limit of 32. Both analysis sources use the same measurements and reports.

`POST /api/land/analyses/stream` emits newline-delimited JSON stage, result, and error events. It shares validation, processing limits, Earth Engine measurements, and result storage with the synchronous endpoint. The frontend uses these stages for land analysis and the existing job status for radar analysis. Archive loading, model scenarios, and AI requests show their own indeterminate progress.

`GET /api/land/analyses/{id}/terrain` reads the cached demo grid or samples Copernicus GLO-30 within a live profile boundary. `frontend/src/TerrainView.tsx` draws the data as a rotatable 3D surface and preserves the view while switching result tabs. Rebuild the two offline grids with `.venv/Scripts/python.exe -m scripts.cache_land_terrain`.

`POST /api/land/analyses/{id}/scenario` optionally returns weekly storage percentages on the shared terrain sampling grid alongside its original 2D images and statistics. The route computes the grid without an elevation request. The client requests elevation separately when opening 3D replay and drives the chart, both map views, and playback from the same selected frame.

The land evidence provider serves `inspection`, `history`, and `plot` under the existing profile routes. It runs Sentinel-2 and Landsat comparisons on the existing equal-area grid. Plot facts use JRC water extent and Copernicus elevation. `POST .../monsoon/{year}` uses the same scenario solver with daily CHIRPS rainfall from the cell near the study centroid, starting on July 1. Each evidence route tries the packaged demo result first and shares the live processing limit. The frontend retains up to ten recent live plot IDs for comparisons in the current session.

The queue allows two simultaneous jobs and retains at most 24 recent outcomes, with a one-hour retention limit. Historical results bypass the queue. Their IDs are derived from the slug, manifest and image bytes, so unchanged bundles keep their layer and report links across restarts. SQLite persistence of new jobs and GeoJSON flood vectorization are pending.

On Vercel, `vercel.json` serves the Vite build and sends `/api` to `api/index.py`. That entry point serves the packaged evidence without Earth Engine credentials or cross-request worker state. The synthetic radar case uses a deterministic ID and can be recomputed by any worker. The local entry point retains the asynchronous job workflow.

Each bundled historical directory contains `event.json` and three aligned RGBA PNGs named `before.png`, `after.png`, and `change.png`. Use a successful verified API result when preparing a manifest. Set `schema_version` to `1`, record the published `reference_url` and any pairing `rejections`, and omit the transient `id`, `layers`, and `cached_event` fields from `result`. The app regenerates reports from the bundled data and does not fetch the linked reference image.
