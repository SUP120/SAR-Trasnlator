# Project context

SAR Translator is an ASTRA 2026 hackathon prototype for turning Sentinel-1 observations into understandable evidence of possible surface-water expansion. A flood-claim analyst is the primary persona. Disaster-management staff, agri-business teams, and the public are secondary users.

The P0 flow is study area and dates → comparable observations → possible flood mask, stats, and quality rubric → English or Hindi explanation → one-page PDF. A local demo must eventually load at least three precomputed real events without network access. The flood mask is a screening estimate for field verification. The product excludes claim decisions and damage valuation.

The intended stack is React/Vite/TypeScript, Leaflet, FastAPI/Pydantic, and a separate SAR provider interface with Earth Engine first and cached events for offline demos. The PRD covers later SQLite storage, bilingual explanation templates and optional LLM, and ReportLab exports. See [the PRD](../PRD.md) for scientific defaults, priorities, and submission requirements. The actual architecture and current progress are recorded separately.
