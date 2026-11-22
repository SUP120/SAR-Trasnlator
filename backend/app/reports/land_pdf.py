from html import escape
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..land import LandProfile, Narrative

LIMITATIONS = (
    "Sentinel-2 NDVI estimates greenness. NDMI is a vegetation moisture proxy. Optical water can include existing water.",
    "NASA SMAP surface soil moisture is a regional model-assisted estimate on an approximately 11 km catalog grid.",
    "Dynamic World land cover is an AI classification. Reported shares use classified cells. Only scene labels with at least 0.55 top-class probability were retained.",
    "Optical image offsets describe apparent alignment at 30 m resolution. Seasonal appearance and scene registration can affect them. Field confirmation is required for ground motion.",
)


def template(profile: LandProfile) -> Narrative:
    usable = [row for row in profile.observations if row.ndvi is not None]
    if not usable:
        return Narrative(source="template", text="Clear optical coverage was insufficient for a vegetation or water comparison. "
                         "Check the observation coverage and try a longer period.")
    latest = usable[-1]
    return Narrative(source="template", text=f"The latest usable optical period starts on {latest.start.isoformat()}. "
                     f"Its mean vegetation index is {latest.ndvi:.3f} and clear coverage is {latest.clear_pct:g}%. "
                     "Use the dated measurements and coverage to interpret changes in the study area.")


def build_land_report(profile: LandProfile) -> bytes:
    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, title="SAR Translator land analysis", author="SAR Translator",
                                 rightMargin=34, leftMargin=34, topMargin=38, bottomMargin=32)
    style = getSampleStyleSheet()
    narrative = profile.narrative or template(profile)
    source = {"template": "Template", "ai": "AI-generated", "cached_ai": "Cached AI-generated"}[narrative.source]

    def para(text: str, name: str = "BodyText") -> Paragraph:
        return Paragraph(escape(text), style[name])

    def fmt(value: float | None, decimals: int = 2) -> str:
        return f"{value:.{decimals}f}" if value is not None else "—"

    entries = [["Month", "Clear %", "NDVI", "NDMI", "Water %¹", "Soil %²", "Leading cover³"]]
    for row in profile.observations:
        label = max(row.land_cover_pct, key=row.land_cover_pct.__getitem__) if row.land_cover_pct else None
        leading = f"{label} {row.land_cover_pct[label]:g}%" if label else "—"
        entries.append([row.start.strftime("%Y-%m"), fmt(row.clear_pct), fmt(row.ndvi, 3), fmt(row.ndmi, 3),
                        fmt(row.mapped_water_pct), fmt(row.soil_moisture_pct), leading])
    table = Table(entries, colWidths=[56, 55, 47, 47, 62, 57, 197], repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#18393f")),
                               ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                               ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                               ("FONTSIZE", (0, 0), (-1, -1), 9),
                               ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eff5f3")]),
                               ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    bounds = profile.aoi.coordinates[0]
    west, east = min(lon for lon, _ in bounds), max(lon for lon, _ in bounds)
    south, north = min(lat for _, lat in bounds), max(lat for _, lat in bounds)
    content = [para(profile.title, "Title"), para(f"Study area {profile.area_km2:.2f} km² · 30 m comparison grid"),
               para(f"Bounds {west:.4f}° to {east:.4f}° longitude and {south:.4f}° to {north:.4f}° latitude"),
               para(f"{source} summary", "Heading2"), para(narrative.text),
               para("Monthly observations", "Heading2"), table,
               para("¹ Share of clear pixels. ² Regional volumetric soil moisture. ³ Share of classified pixels."),
               para("Sources and limitations", "Heading2")]
    content.extend(para(note) for note in LIMITATIONS)
    if offsets := [row for row in profile.observations if row.image_offset is not None]:
        last = offsets[-1]
        offset = last.image_offset
        if offset:
            content.append(para(f"Latest apparent image offset {offset.east_m:+d} m east and {offset.north_m:+d} m north, "
                                f"from {offset.from_period} to {last.start}, with {offset.matched_blocks} agreeing blocks."))
    content.extend([Spacer(1, 6), para("Sources: modified Copernicus Sentinel-2 data, Dynamic World (Google/WRI), NASA SMAP L4."),
                    para("Use the separate Sentinel-1 flood analysis for event-specific flood screening.")])
    document.build(content)
    return buffer.getvalue()
