# SAR Translator

SAR Translator is a prototype for screening possible surface-water change using Sentinel-1 radar. It lets you draw and measure a study area, select an observation window, compare before and after layers, inspect the quality rubric, and download a one-page evidence report in English or Hindi.

The app includes three cached cases using real Sentinel-1A observations. Each result retains its observation dates, processing parameters and quality rating. Published flood maps support qualitative comparison, and Balasore has a quantitative comparison with an independent satellite product.

- North Guwahati, Assam, June 2022. [Published comparison map](https://sentinel-asia.org/EO/2022/article20220615IN/MBRSC/MBRSC_North-Guwahati.jpg)
- Central Gujarat, August 2024. [Published comparison map](https://sentinel-asia.org/EO/2024/article20240827IN/MBRSC/MBRSC_INDIA_FLOOD_27th_AUG24.jpg)
- Balasore, Odisha, October 2024. [Published comparison map](https://sentinel-asia.org/EO/2024/article20241025IN/MBRSC/MBRSC_INDIA-FLOOD-MAP_25TH_OCTOBER.jpg)

## Run locally on Windows

Use Python 3.11+ and Node.js 22.12+. From the project root, start FastAPI in one PowerShell terminal.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal, start the React app.

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run dev -- --host 127.0.0.1
```

Open [the workspace](http://127.0.0.1:5173/) or [the API documentation](http://127.0.0.1:8000/docs). **Satellite** starts selected. Use **+ / −**, the scroll wheel, or pinch to zoom. Drag to pan. **Terrain** and area validation work without internet access once dependencies are installed. From the workspace, select **Guwahati**, choose **Draw rectangle** on the map, place two close opposite corners, and select **Validate study area**. For keyboard drawing, use the arrow keys to pan, Enter to place a point at the map center, and Shift+Enter to finish a polygon.

Choose a **Historical example** and click **Open offline**. Switch among the three layers, lower **Overlay opacity** to see the basemap through the radar image, inspect the dates and quality factors, and select English or Hindi before downloading the PDF. Cached cases need only the local app after installation. You can also select **Run synthetic example** for a practice run. New analysis jobs expire on server restart or when their retention period ends. Bundled historical links survive a restart.

## Explore land history and scenarios

Open **Land analysis** and choose a role and purpose. Select **Farmland demo** (near Ludhiana, Punjab) or **Dry-land demo** (west of Jaisalmer, Rajasthan). Both include six real monthly observations from October 2024 to March 2025 and work with Earth Engine disabled. Results open at the **Overview**, where the selected purpose determines the evidence and field checks. **Satellite data** shows the interactive timeline. **Scenarios** and **Report** open at the same level. To analyze another site, draw and validate the boundary, choose an end date and a number of months, then select **Run land analysis**. **Change focus** lets you reinterpret the same observations without repeating the satellite query.

When an AI provider is configured, the overview automatically requests a separate personalized suggestion. The request includes the selected role, purpose, and derived observations. The built-in guidance is available offline, and the measured PDF remains available from **Report**.

Open **3D terrain** in a land result to explore the selected boundary's elevation surface. Drag to rotate or tilt, use the zoom buttons, or adjust vertical exaggeration. The scale labels show sampled elevations in metres relative to EGM2008. The surface can include trees and buildings. Both demos include offline grids, and new studies obtain elevation on demand from Earth Engine. [Copernicus DEM GLO-30](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_DEM_GLO30_2024_1).

Select a rainfall or drought preset, adjust the assumptions, and run the scenario. Press **Play** or move the timeline slider to view the resulting storage map by week. The model starts from the selected storage assumption and uses the most recent sufficiently classified Dynamic World grid. It assumes land-cover-dependent infiltration and constant daily demand. It estimates storage and overflow under those assumptions. It does not forecast weather, flood extent, crop losses, or water availability.

Choose **3D replay** after running the scenario to view the same week on the elevation surface. Orange shows lower modeled storage, blue shows higher storage, and gray marks missing model coverage. Use the chart, slider, or **Play** to change the week. Both demo replays work offline.

- **Field inspection** flags groups of crop pixels with a clear drop in greenness compared with the same dates in the previous three years. Select a numbered patch to see its area and a point to visit. The orange flag suggests an inspection. Greenness can change due to harvest, irrigation, damage, and other causes.
- **Compare plots** pairs the current analysis with a demo or a recent analysis from this session. To compare two drawn plots, run both using the same end date and number of months, then select the first plot while viewing the second. The cards include slope, where water appeared in the JRC 1984–2021 record, and crop and built-up shares for matching observation dates.
- **Use past monsoon rain** under **Scenarios** drives the soil-water model with daily regional CHIRPS rainfall estimates from July 1 for the chosen duration. Both demos include July 2024. Live sites and other years require Earth Engine. The simulator still uses chosen starting conditions and the land-cover baseline shown.
- **30 years ago** compares the same three complete calendar months on an aligned Landsat grid. The demos compare January–March 1995 and 2025. Move the slider to reveal each image and expand the date details for scene sources.

Refresh the derived evidence for both offline demos with `.venv/Scripts/python.exe -B -m scripts.cache_land_evidence` after configuring Earth Engine.

The land PDF contains the dated observations, coverage and sources. The offline demo PDFs have cached AI summaries grounded in their measured results. An arbitrary study area can use the measured template report without a key. Set `GROQ_API_KEY` in the API process to enable **Generate AI summary** using Groq's free-plan `openai/gpt-oss-20b` model, subject to account limits. Override the model with `LAND_GROQ_MODEL`. If no Groq key is configured, `LAND_LLM_API_KEY` enables OpenAI and `LAND_LLM_MODEL` overrides its default `gpt-4.1-mini`. The AI request sends derived monthly statistics and dates. It omits the boundary, asset IDs and images. Keep keys server-side. [Groq limits](https://console.groq.com/docs/rate-limits).

The land timeline uses cloud-screened Sentinel-2 for NDVI, NDMI, and mapped open water, NASA SMAP L4 for a regional soil moisture estimate, and Google/WRI Dynamic World for land-cover classes. NDMI tracks vegetation moisture. SMAP’s approximately 11 km catalog grid is regional. Apparent optical offsets are reported at 30 m grid resolution when enough textured blocks agree. They need independent confirmation for ground movement. The separate Sentinel-1 workflow screens for potential event flooding. [Sentinel-2](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S2_SR_HARMONIZED) · [NASA SMAP](https://developers.google.com/earth-engine/datasets/catalog/NASA_SMAP_SPL4SMGP_008) · [Dynamic World](https://developers.google.com/earth-engine/datasets/catalog/GOOGLE_DYNAMICWORLD_V1).

To rebuild the measured demo bundles with Earth Engine, run `.venv/Scripts/python.exe -m scripts.cache_land_demos` from the project root. Review the new observations before attaching a new AI summary. The rebuild clears old summaries since they were generated from the previous measurements.

## Scientific evaluation

| Case | Reference | Eligible area | Precision | Recall | F1 | IoU |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Balasore, 28 Oct 2024 | JAXA ALOS-2 flood proxy, 26 Oct 2024 | 99.60% | 35.21% | 30.28% | 32.56% | 19.44% |

These figures measure agreement for one event and include a two-day acquisition gap. [Methods, exclusions, and reproduction steps](validation/results.md).

## Verify locally

Run these from the project root.

```powershell
.venv\Scripts\python.exe -m pytest backend/tests -q
npm.cmd --prefix frontend run build
```

## Configuration

The backend reads process environment variables. `MAX_AOI_KM2` defaults to `100`. `ALLOWED_ORIGINS` accepts comma-separated origins for a separately hosted frontend. In development and preview, Vite proxies `/api` to `127.0.0.1:8000`. To override the API URL, set `VITE_API_BASE_URL` before starting or building Vite.

The South Asia map uses the EOxCloudless Sentinel-2 2016 mosaic for online satellite imagery. The imagery has 10 m detail and native tiles through zoom level 14. Closer zoom enlarges the same imagery. The bundled Natural Earth terrain fills in where satellite tiles are unavailable. Set `VITE_BASEMAP_URL` and `VITE_BASEMAP_ATTRIBUTION` together to use a different licensed XYZ tile service. Set `VITE_BASEMAP_MAX_NATIVE_ZOOM` to that provider's native limit (default `18` for a custom provider). [EOxCloudless documentation](https://cloudless.eox.at/documentation/faq).

### Enable live Sentinel-1 analysis

Register or select an [Earth Engine-enabled Cloud project](https://developers.google.com/earth-engine/guides/access) and authenticate locally. Run the following from the project root in the same terminal that starts the API.

```powershell
.venv\Scripts\python.exe -m pip install -r backend\requirements-earth-engine.txt
.venv\Scripts\earthengine.exe authenticate
$env:EE_PROJECT_ID = '<your-project-id>'
.venv\Scripts\python.exe scripts\check_access.py
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

The probe prints acquisition dates, platforms, orbit properties, and dataset bands. Change its starting area and dates with `--bbox WEST SOUTH EAST NORTH`, `--start YYYY-MM-DD`, and `--end YYYY-MM-DD` (exclusive). Local authentication stores credentials outside the repository. [Google's authentication guide](https://developers.google.com/earth-engine/guides/auth).

With a project set, the app offers **Run Sentinel-1 analysis** for validated study areas. `PROCESSING_SCALE_M` defaults to `10`, and `SAR_PROVIDER=cached` disables live submission while keeping the historical and synthetic examples available. The 7-, 30-, and 90-day presets end on the most recent acquisition day found for the area. The custom range includes the selected end date and uses the event date to split the before and after periods.

## Basemap data

The bundled assets use [Natural Earth public-domain data](https://www.naturalearthdata.com/about/terms-of-use/). Vector inputs come from [Natural Earth vector v5.1.2](https://github.com/nvkelso/natural-earth-vector/tree/v5.1.2/geojson), and terrain uses [Gray Earth with Shaded Relief and Flat Water v3.2.0](https://www.naturalearthdata.com/downloads/50m-gray-earth/50m-gray-earth-with-shaded-relief-and-water/). The region is cropped, linework is simplified, and terrain is reprojected for Leaflet.

To rebuild the assets, save `ne_50m_admin_0_countries.geojson`, `ne_50m_admin_1_states_provinces_lines.geojson`, `ne_10m_rivers_lake_centerlines.geojson`, `ne_10m_populated_places.geojson`, and [the Gray Earth archive](https://naturalearth.s3.amazonaws.com/50m_raster/GRAY_50M_SR_W.zip) to `data/local/natural-earth/`. Install Pillow in the Python environment and run `python scripts/build_basemap.py` from the project root.

## Project documentation

See the [PRD](docs/PRD.md), [implementation status](docs/agent-memory/PROGRESS.md), and [handoff](docs/agent-memory/HANDOFF.md).

## Contributors

- Supriyam Kumar
