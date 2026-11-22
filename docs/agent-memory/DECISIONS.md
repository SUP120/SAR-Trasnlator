# Decisions and verification

## D-001 · Scope of the first increment

Build the local workspace, a health endpoint, and verified AOI validation before requesting live imagery. Use React Leaflet 5 with React 19 and lightweight Leaflet event handling for the two drawing tools. Plain CSS keeps dependencies small at this stage. The bundled Natural Earth basemap and example location search work offline.

Use WGS84 ellipsoidal area for the analysis cap and display. Reject extra dimensions, open rings, self-intersections, and polygons that span the antimeridian. An API test compares area to a local Lambert azimuthal equal-area projection.

## D-002 · Earth Engine catalog checks

| ID | Status | Evidence |
| --- | --- | --- |
| V1 | Verified by live query | The 2026-11-21 probe observed C and D in the last 30 days. The latest observed acquisitions were 10:58:11 UTC for C and 11:45:45 UTC for D on the probe date. [Sentinel-1 catalog](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S1_GRD). |
| V2 | Verified by live query | The Guwahati date window returned 14 scenes. Metadata contained orbit pass, relative orbit, platform, instrument mode and polarization. The first scene had `VV`, `VH` and `angle`. |
| V3 | Verified by live query | [JRC water](https://developers.google.com/earth-engine/datasets/catalog/JRC_GSW1_4_GlobalSurfaceWater) returned `occurrence` and `seasonality`, [WorldCover v200](https://developers.google.com/earth-engine/datasets/catalog/ESA_WorldCover_v200) returned `Map`, [MERIT Hydro](https://developers.google.com/earth-engine/datasets/catalog/MERIT_Hydro_v1_0_1) returned `hnd`, and the supported [GLO-30 2024_1](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_DEM_GLO30_2024_1) returned `DEM`. |
| V4 | Partial | Authenticated catalog, metadata, and pixel requests succeeded with the owner-provided project. Registration category and quota tier remain unverified. |
| V5 | UNVERIFIED | Public search did not establish the exact hackathon rules. Request the official link or rulebook in UA-001. |
| V6–V8 | Pending | Indian data sources, Copernicus Data Space limits, and the competitive scan belong to later work. |

The probe defaults to a Guwahati study area and a 2022 window as an exploration starting point. A real cached event needs verified comparable scenes and a reference map.

## D-003 · Shared flood processing and live defaults

Group scenes by orbit direction, relative orbit, mode, and the complete polarization set. Compare the shared footprint of the selected before/after composites and prefer a single platform on coverage ties. Cap each composite at six scenes closest to the event. Report shared footprint and jointly valid pixels separately.

Earth Engine builds speckle-filtered median VV composites and supplies auxiliary bands plus `pixelArea` on an EPSG:6933 grid. NumPy and SciPy apply the water, terrain and eight-connected cluster rules locally. The same classification and area engine runs on the synthetic inputs. The grid is limited to 1.5 million cells and 4,096 cells per side to stay within interactive compute and memory limits. Percentages use the area of sampled AOI cells. Defaults are pending validation against real floods. [Earth Engine `computePixels` reference](https://developers.google.com/earth-engine/reference/rest/v1/projects.image/computePixels).

A live projection probe verified WKT1_GDAL for the EPSG:6933 definition after Earth Engine rejected the authority code. The adapter now provides the same WKT in the composite projection and REST `crsWkt`. The geographic grid, thresholds, area weighting and local reprojection remain equivalent. [Earth Engine PixelGrid reference](https://developers.google.com/earth-engine/reference/rest/v1/PixelGrid).

Use deterministic explanations in both languages. The numerical facts come directly from results. Hindi reports use ReportLab with HarfBuzz shaping and Noto Sans Devanagari under SIL OFL. Regenerate reports from the same PNGs shown in the map to preserve alignment and provenance.

## D-004 · Search and deployment

The app uses its bundled example search for now. Before introducing a live geocoding endpoint, use a self-hosted or approved service and account for deployment limits, attribution and privacy. Public Nominatim limits application traffic and disallows autocomplete. [Nominatim usage policy](https://operations.osmfoundation.org/policies/nominatim/).

## D-005 · First live comparison

The 2026-11-21 API run used North Guwahati bounds `[91.707, 26.216, 91.748, 26.255]` and the ascending Sentinel‑1A relative orbit 41 pair on 4 and 16 June 2022. It returned 358.02 ha of possible water change, 20.13% of the 17.7856 km² sampled area, and 100% shared valid coverage. It rated Low because each period contained one scene. Processing took about 20 seconds for the single observed request.

Aligned the published map to the study area using its printed WGS84 graticule. Major areas of detected change lined up broadly in the west, centre and east. The two mapped footprints differ, and the reference uses the same Sentinel-1 dates and states that its accuracy has not been validated. Use this result as a qualitative check only. Raw probe and verification outputs live under ignored `data/local/live-verification/`. [MBRSC North Guwahati flood map](https://sentinel-asia.org/EO/2022/article20220615IN/MBRSC/MBRSC_North-Guwahati.jpg).

## D-006 · Offline event playback

Ship the verified result metadata and app-generated map layers from the North Guwahati run as a roughly 450 KiB bundle. Preserve scene IDs, processing parameters, areas, warnings, and the original quality rating. Keep the cached label on the map, results, and report. Store the third-party reference as a link so it is optional during offline use. Reuse the existing results and report endpoints with a stable content-derived ID.

## D-007 · Gujarat and Odisha historical cases

- Central Gujarat, August 2024. The study bounds were `[73.087, 22.155, 73.145, 22.208]`. Sentinel-1A descending relative orbit 34 used 23 July and 16 August before, and 28 August after. The app calculated 384.84 ha of possible water change and 100% shared valid coverage. The largest change groups in the east and south broadly align with the published map. [MBRSC Gujarat reference](https://sentinel-asia.org/EO/2024/article20240827IN/MBRSC/MBRSC_INDIA_FLOOD_27th_AUG24.jpg).
- Balasore, Odisha, October 2024. The study bounds were `[86.927, 21.49, 86.998, 21.555]`. Sentinel-1A descending relative orbit 48 used 29 August, 10 and 22 September, 4 and 16 October before, and 28 October after. The app calculated 554.95 ha of possible water change and 100% shared valid coverage. The western, central and eastern patches broadly align with the published map. [MBRSC Odisha reference](https://sentinel-asia.org/EO/2024/article20241025IN/MBRSC/MBRSC_INDIA-FLOOD-MAP_25TH_OCTOBER.jpg).

## 2026-11-21 · Default to satellite imagery

Use the attributed EOxCloudless 2016 Sentinel-2 layer because it offers cloud-free satellite context through native zoom 14 under CC BY 4.0. Allow zoom to 18 for drawing, with imagery enlarged beyond the native limit, and retain the bundled terrain beneath the tiles. Keep a Terrain switch for offline use, a custom provider option, and independent radar overlay opacity. [EOxCloudless documentation](https://cloudless.eox.at/documentation/faq).

## 2026-11-21 · Measure agreement with an independent Balasore product

Replay the cached settings on the original 10 m equal-area grid and compare the full prediction inside the AOI, finite radar coverage and the JAXA product region. The two-day lag and JAXA's automatic mapping limit interpretation. Precision was 35.21% and recall was 30.28%. Keep the radar parameters and the observation quality rubric at their existing values. [Validation methods and results](../../validation/results.md).

## 2026-11-22 · Extend the same app with monthly land observations

Reuse the AOI, Earth Engine access and equal-area grid. On a 30 m grid compute monthly median Sentinel-2 NDVI and NDMI and an open-water indicator (MNDWI greater than 0 and NDVI below 0.2). Screen SCL to classes 4, 5 and 6, keep up to 18 scenes per month sorted by scene-wide cloud fraction, and suppress aggregate optical indicators below 20% clear area. Dynamic World takes the mode of scene labels with top probability at least 0.55 and reports each class share over classified cells. SMAP supplies a monthly regional surface soil moisture estimate at the study area centroid on its approximately 11 km catalog grid. The three distinct measurements must retain separate units and caveats. [Sentinel-2](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED) · [Dynamic World](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1) · [SMAP L4](https://developers.google.com/earth-engine/datasets/catalog/NASA_SMAP_SPL4SMGP_008).

Report optical image offset only with agreement across at least three textured blocks, a correlation peak of at least 0.8, a 0.05 lead over the runner-up, and at least 60% agreement among accepted blocks. This prototype uses grid-cell offsets, rejects matches at the search boundary, and does not infer subsidence or confirmed ground motion. The comparison threshold has a translated synthetic regression fixture and has not been calibrated with field displacement data.

Use October 2024 to March 2025 for both demo regions. In the March baseline, the Punjab site had 86.38% crops among classified cells (69.31% area classified). The Rajasthan site had 98.53% bare ground among classified cells (37.13% area classified). Store derived RGB thumbnails, scene IDs, metrics, and the baseline class grid in the compact offline bundles. Cache AI-written prose grounded in those observations. Numbers in the PDFs always come from the backend measurements.

The scenario balance uses the configured initial storage, a class-based infiltration fraction, weekly rain distributed evenly by day, an upper storage cap, and constant daily water demand. Scenario frames describe assumed conditions. They do not predict field moisture or flood extent. Keep current radar thresholds and grading intact.

## 3D elevation surface

The scenario replay colors the elevation mesh using weekly modeled storage as a percentage of capacity. Sample the original modeled cell containing each terrain sample in EPSG:6933 and show gray faces where any vertex lacks model coverage. The elevation surface stays fixed as the storage color changes. The visual sampling does not feed back into the reported statistics.

## Satellite evidence for field visits, comparisons, and monsoons

Field inspection compares the latest usable Sentinel-2 period with per-cell median NDVI for the same dates in the previous three years. Require at least two clear prior years per sample, at least 20% shared area, Dynamic World crops in at least one period, reference NDVI of 0.25 or more, a drop of at least 0.15, and four connected 30 m cells. Rank up to eight patches by size. These are screening thresholds. The synthetic connectivity check and real Punjab archive verify the workflow, and field diagnosis remains uncalibrated.

Use Landsat 5 and Landsat 8/9 Collection 2 surface reflectance, with cloud, shadow, snow, and saturation masking, for the same three complete calendar months thirty years apart. Require at least 20% clear coverage per preview. Plot water uses JRC maximum detected extent from 1984 to 2021 over samples with valid observations. Compare class shares only for matched date windows and show coverage. CHIRPS v2 daily totals drive the existing model without spreading each weekly total across days. Treat those rainfall estimates as regional and label the modeled soil-water output separately.

Reuse the radar workflow's Copernicus GLO-30 surface data. Sample within the selected land polygon on the existing equal-area grid at 30 m or coarser, with at most 56 cells per side. Preserve null cells. Archive each demo grid with its existing land result. Canvas projects and depth-sorts local faces without a new dependency. Initial vertical exaggeration is adjusted to show relief and remains user-controlled. Display the sampling scale, surface model limitation, and Copernicus credit. [Dataset description](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_DEM_GLO30_2024_1).

Each run includes the published baseline date and additional pre-event observations in its median composite. Both scored Low because each post-event period had one observation. The comparisons used the graticules on the published JPEGs, which resolve the selected areas only coarsely. Their accuracy is unvalidated, and both comparisons share the same post-event Sentinel-1 acquisition. The app bundle contains the computed layers and references as links. The downloaded JPEGs and comparison panels stay in the ignored verification folder.
