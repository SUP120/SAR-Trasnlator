# Handoff

## Last updated and current phase

2026-11-22 · Monthly land analysis and two offline demos available locally.

## Work in this session

Added monthly satellite land observations, real farmland and dry-land archives, a weekly scenario animation, and land PDFs with cached demo AI narratives. Live AI summaries use an optional backend key.

## Completed and verified

- The flood and land views use solid charcoal and slate surfaces. Land results have underlined navigation and neutral measurement cards. The farmland view was verified in the browser.
- Flood results lead with the mapped area and three radar images. Land results lead with a vegetation chart and satellite image. Detailed evidence and scenario controls expand on demand.
- The land chart now switches among vegetation greenness, vegetation moisture, and regional soil moisture. Flood summary cards separate area, shared coverage, and quality. Verified browser interactions and the narrow layout.
- The scenario view charts modeled weekly storage and links the selected week to its map and statistics. Verified both presets in the browser.
- A role and purpose selection opens a focused land overview. Satellite data, scenarios and reports are adjacent views. Verified a farmer-to-buyer switch on the same archived observations. The optional personalized Groq call passed a mocked integration test and still needs a live key.
- The live land and flood buttons now show progress panels with real server stages. Verified both with Earth Engine and confirmed the progress panels cleared when results appeared.
- The 3D terrain view displays Copernicus elevation for live land profiles and both cached demos. Browser checks covered both elevation ranges and the rotation and zoom controls.
- Scenario results now offer a 3D replay over the elevation surface. Browser checks covered both demos, chart and map synchronization, and playback. The offline suite passed 37 tests.
- The scenario and satellite screens use everyday language for measurements, with short notes for percentages, excess water, and map colors. Browser checks covered both map views and the satellite chart.
- The 3D terrain view explains its height colors and height stretching before presenting the source details. The replay explains its separate soil-water colors. Both guides were verified in the browser.
- The GitHub-linked Vercel project serves the public demo at https://sar-translator.vercel.app. The production API uses packaged observations and a stateless practice case. Live Earth Engine analyses continue through the local service.
- Both offline land demos include field-inspection patches, comparable plot facts, a July 2024 rainfall replay, and an aligned 1995–2025 Landsat comparison. Browser checks covered all four views, and the offline backend suite passed 40 tests.

- 31 pytest checks passed with Earth Engine disabled and the Vite production build passed. Offline tests cover the three flood cases, both land demos, their reports, and distinct scenario runs.
- The in-app browser opened both land cases, switched the imagery month, ran both presets and played the resulting frames. The localhost frontend and API on ports 5173 and 8000 were left running for the owner.
- A new live Earth Engine request reproduced the last three months of the Punjab archive. The demo narratives were checked against the recorded metrics. See [PROGRESS](PROGRESS.md) for the results.
- The Balasore replay matched the cached change image exactly. The ALOS-2 flood proxy from two days earlier yielded 32.56% F1 and 19.44% IoU. [Reproducible results](../../validation/results.md).

## Partially implemented

- `backend/app/providers/earth_engine.py` supports live metadata and pixels. The first case was verified. General scientific performance, latency, quota and deployment authentication are pending.
- `backend/app/explanations.py` implements grounded bilingual templates. A native-language pass and optional LLM remain pending.
- Land reports have a verified measured fallback and cached AI summaries. Live AI uses `GROQ_API_KEY` when configured and otherwise supports `LAND_LLM_API_KEY` for OpenAI. After the owner configures a replacement Groq key, verify one live summary and the PDF source label. Apparent optical image offsets are not calibrated for scientific ground-motion analysis.
- Live place search, flood polygon download, persistence for new jobs, and multi-event scientific validation are pending.

## Files modified this session

- `backend/app/{land.py,land_narrative.py,api/land.py,providers/land_optical.py,reports/land_pdf.py,main.py}` and `backend/tests/test_land.py`.
- `frontend/src/{App.tsx,api.ts,LandWorkspace.tsx,landApi.ts,land.css}`.
- `scripts/cache_land_demos.py`, `data/land_demos/`, `README.md`, and project memory.

## Current bugs and blockers

Local Earth Engine authentication and the live workflow are resolved. See [BUGS](BUGS.md) for the fixes, Windows sandbox, and test dependency warning. The local Git repository uses `main` and the `SUP120/SAR-Trasnlator` remote.

## Install, run, and test

Follow [README](../../README.md). From the project root run `.venv/Scripts/python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000`. In a second terminal run `npm.cmd --prefix frontend run dev -- --host 127.0.0.1`. Tests are `.venv/Scripts/python.exe -m pytest backend/tests -q` and `npm.cmd --prefix frontend run build`.

## Exact next task

Define and record event-disjoint tuning and held-out groups from Sen1Floods11 and run the existing thresholds as a baseline. Verify that the input scenes can be represented by the prototype's before/after procedure. Record exclusions for incompatible events before adjusting parameters.

## Continuation steps

1. Check event files, label licensing, and availability of comparable baseline scenes.
2. Record a split by event so overlapping tiles and nearby acquisition dates cannot straddle the two groups.
3. Record per-event and aggregate baseline metrics in `validation/results.md` before threshold calibration.

## Warnings and unfinished work

Each historical case retains its Low rating because the post-event period had one usable scene. General scientific accuracy remains unverified. New job results are in memory. Bundled event links remain stable until the bundle is changed.

## Open owner actions

UA-002 and UA-003 are complete for local work. UA-001 remains open for the official ASTRA rules. UA-004 enables live AI narratives for new land studies. See [USER_ACTIONS](USER_ACTIONS.md).
