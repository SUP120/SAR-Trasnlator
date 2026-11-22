# Owner actions

## UA-001 [OPEN] · Hackathon rules and deadline

Opened 2026-11-21. Share the organizer's page or rulebook covering dates, required deliverables, judging, team size, and data-source constraints. Record verified rules in DECISIONS and apply them to the submission plan.

## UA-002 [DONE] · Earth Engine Cloud project

Opened 2026-11-21. Enable the Earth Engine API and register the project for the applicable access category through [Earth Engine project setup](https://developers.google.com/earth-engine/guides/access). Record the project ID and the displayed quota tier. Verify access with `scripts/check_access.py` after authentication.

API access was verified on 2026-11-21 with catalog queries and a live raster analysis. Set `EE_PROJECT_ID` locally to an Earth Engine-enabled project. Registration category and quota tier were not inspected.

## UA-003 [DONE] · Earth Engine authentication

Opened and verified 2026-11-21. The owner completed `.\.venv\Scripts\earthengine.exe authenticate --auth_mode=localhost`. `scripts/check_access.py` and a live analysis both succeeded. Credentials remain in the local credential store. For deployment later, see [Google's service-account guidance](https://developers.google.com/earth-engine/guides/service_account).

## UA-004 [PENDING] · Optional LLM credentials

The offline land demos include cached AI summaries and can generate measured PDFs without a key. To enable new AI summaries for arbitrary study areas through Groq, set a replacement `GROQ_API_KEY` in the backend process and restart it. Revoke any shared key in the Groq Console. Verify by choosing **Generate AI summary** on a live land result and checking the report source. The existing English and Hindi flood reports independently use templates.

## UA-007 [DONE] · Developer tools

Verified 2026-11-21. Python 3.12.7, Node.js 22.18.0, npm 10.9.3, and Git 2.53.0 are installed.
