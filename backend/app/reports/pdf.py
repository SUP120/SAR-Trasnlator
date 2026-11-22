from functools import lru_cache
from io import BytesIO
from pathlib import Path
from re import compile
from threading import Lock
from xml.sax.saxutils import escape

from PIL import Image
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from shapely.geometry import shape

from ..analysis import AnalysisResult
from ..aoi import WGS84
from ..explanations import Language, dates_used, explain
from ..pipeline.raster import LAYER_NAMES, RenderedLayers

WIDTH, HEIGHT = A4
MARGIN = 34
INNER = WIDTH - 2 * MARGIN
INK = HexColor("#162637")
MUTED = HexColor("#52657b")
TEAL = HexColor("#0e6d62")
LINE = HexColor("#dce5ed")
PALE = HexColor("#f0f5f8")
FONT_PATH = Path(__file__).parent / "assets" / "NotoSansDevanagari-Regular.ttf"
_shape_lock = Lock()
DEVANAGARI = compile(r"[\u0900-\u097f]")


@lru_cache(maxsize=1)
def _hindi_font() -> str:
    pdfmetrics.registerFont(TTFont("Devanagari", str(FONT_PATH), shapable=True))
    return "Devanagari"


def _map_image(pdf: canvas.Canvas, payload: bytes, bounds, x: float, y: float, width: float, height: float) -> None:
    image = Image.open(BytesIO(payload))
    scale = min(width / image.width, height / image.height)
    drawn_width, drawn_height = image.width * scale, image.height * scale
    left, bottom = x + (width - drawn_width) / 2, y + (height - drawn_height) / 2
    painted = Image.new("RGB", image.size, "#c4d4dd")
    painted.paste(image, mask=image.getchannel("A"))
    pdf.setFillColor(PALE)
    pdf.roundRect(x, y, width, height, 6, fill=1, stroke=0)
    pdf.drawImage(ImageReader(painted), left, bottom, drawn_width, drawn_height)
    (south, west), (north, east) = bounds
    lat = (south + north) / 2
    _, _, distance_m = WGS84.inv(west, lat, east, lat)
    bar_m = next((step for step in (2000, 1000, 500, 200, 100, 50, 20, 10, 5, 2, 1) if step < distance_m / 3), None)
    pdf.setFont("Helvetica-Bold", 7)
    pdf.setFillColor(INK)
    pdf.setStrokeColor(INK)
    pdf.drawRightString(x + width - 7, y + height - 11, "N")
    pdf.line(x + width - 9, y + height - 15, x + width - 9, y + height - 21)
    pdf.line(x + width - 9, y + height - 15, x + width - 11, y + height - 18)
    pdf.line(x + width - 9, y + height - 15, x + width - 7, y + height - 18)
    if bar_m:
        bar_width = drawn_width * bar_m / distance_m
        pdf.setFillColor(white)
        pdf.rect(x + 4, y + 3, max(bar_width + 12, 33), 13, fill=1, stroke=0)
        pdf.setFillColor(INK)
        pdf.drawString(x + 7, y + 9, f"{bar_m} m")
        pdf.line(x + 7, y + 6, x + 7 + bar_width, y + 6)


def _render(result: AnalysisResult, layers: RenderedLayers, language: Language) -> bytes:
    hindi = language == "hi"
    font = _hindi_font() if hindi else "Helvetica"
    bold = font if hindi else "Helvetica-Bold"
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    pdf.setTitle("SAR Translator - Surface-water evidence")
    pdf.setAuthor("SAR Translator")

    def line(text: str, x: float, top: float, size=9, color=INK, *, heavy=False):
        devanagari = hindi and bool(DEVANAGARI.search(text))
        latin = "Helvetica-Bold" if heavy else "Helvetica"
        pdf.setFont((bold if heavy else font) if devanagari else latin, size)
        pdf.setFillColor(color)
        pdf.drawString(x, HEIGHT - top, text, shaping=devanagari)

    def paragraph(text: str, x: float, top: float, width=INNER, size=9.1, color=INK) -> float:
        devanagari = hindi and bool(DEVANAGARI.search(text))
        style = ParagraphStyle("content", fontName=font if devanagari else "Helvetica", fontSize=size,
                               leading=size + 3.4, textColor=color, shaping=devanagari)
        body = Paragraph(escape(text), style)
        _, height = body.wrap(width, HEIGHT)
        body.drawOn(pdf, x, HEIGHT - top - height)
        return top + height

    explanation = explain(result, language)
    synthetic = result.source == "synthetic"
    pdf.setFillColor(INK)
    pdf.rect(0, HEIGHT - 112, WIDTH, 112, fill=1, stroke=0)
    line("SAR TRANSLATOR", MARGIN, 32, 9, HexColor("#82e3d3"), heavy=True)
    line("जल सतह में बदलाव की रिपोर्ट" if hindi else "Surface-water change evidence", MARGIN, 64, 25, white, heavy=True)
    if synthetic:
        banner = "सिंथेटिक अभ्यास उदाहरण - वास्तविक बाढ़ का प्रमाण नहीं" if hindi else "SYNTHETIC EXAMPLE  |  No evidence of a real flood"
    elif result.cached_event:
        banner = "संग्रहीत सेंटिनल रडार अवलोकन" if hindi else "CACHED SENTINEL-1 OBSERVATIONS"
    else:
        banner = "सेंटिनल रडार अवलोकन" if hindi else "SENTINEL-1 OBSERVATIONS"
    line(banner, MARGIN, 89, 10, HexColor("#82e3d3"), heavy=True)

    center = shape(result.aoi.model_dump()).centroid
    line(f"{result.created_at:%Y-%m-%d %H:%M} UTC  |  ID {result.id[:12]}  |  {language.upper()}", MARGIN, 132, 8, MUTED)
    location = f"{result.title}  |  " if result.cached_event else ""
    line(f"{location}{center.y:.3f}, {center.x:.3f}  |  {result.aoi_area_km2:.3f} km²", MARGIN, 148, 9)
    labels = ("पहले", "बाद में", "बदलाव") if hindi else ("Before", "After", "Detected change")
    panel_width = (INNER - 16) / 3
    for index, (name, label) in enumerate(zip(LAYER_NAMES, labels, strict=True)):
        x = MARGIN + index * (panel_width + 8)
        line(label, x, 173, 9.3, heavy=True)
        _map_image(pdf, layers.pngs[name], result.bounds, x, HEIGHT - 289, panel_width, 108)

    pre, post = dates_used(result.pre), dates_used(result.post)
    cursor = paragraph(f"{labels[0]} - {pre}", MARGIN, 296, size=8)
    cursor = paragraph(f"{labels[1]} - {post}", MARGIN, cursor, size=8)
    platforms = ", ".join(sorted({scene.platform for scene in (*result.pre, *result.post)}))
    geometry = result.geometry
    cursor = paragraph(f"{platforms}   |   {geometry.orbit_pass.title()} {geometry.relative_orbit}   |   "
                       f"{geometry.mode}  {'/'.join(reversed(geometry.polarizations))}", MARGIN, cursor + 2, size=8, color=MUTED)

    stats = result.stats
    tiles = [
        ("संभावित बदलाव" if hindi else "Possible water change", f"{stats.flood_ha:.2f} ha / {stats.flood_km2:.3f} km²"),
        ("क्षेत्र का हिस्सा" if hindi else "Share of sampled area", f"{stats.flood_pct_of_aoi:.2f}%"),
        ("पहले से मौजूद पानी" if hindi else "Pre-existing water", f"{stats.preexisting_water_ha:.2f} ha"),
        ("मान्य डेटा" if hindi else "Shared valid coverage", f"{stats.valid_coverage_pct:.1f}%"),
    ]
    top = cursor + 11
    stat_width = (INNER - 18) / 4
    for index, (label, value) in enumerate(tiles):
        x = MARGIN + index * (stat_width + 6)
        pdf.setFillColor(PALE)
        pdf.roundRect(x, HEIGHT - top - 40, stat_width, 40, 5, fill=1, stroke=0)
        line(label, x + 7, top + 14, 7.4, MUTED)
        line(value, x + 7, top + 30, 8.6, TEAL, heavy=True)

    quality_top = top + 59
    quality = {"High": "उच्च", "Medium": "मध्यम", "Low": "निम्न"}[result.quality.overall] if hindi else result.quality.overall
    line(("अवलोकन गुणवत्ता" if hindi else "Observation quality") + f"  |  {quality}",
         MARGIN, quality_top, 12, TEAL, heavy=True)
    factor_names = ("कक्षा की समानता", "अवलोकन का अंतर", "साझा मान्य क्षेत्र", "प्रति अवधि दृश्य", "भूभाग के कारण बहिष्करण")
    for index, factor in enumerate(result.quality.factors):
        row_top = quality_top + 17 + index * 13.5
        line(factor_names[index] if hindi else factor.name, MARGIN + 1, row_top, 8.5)
        line(factor.observed, MARGIN + 200, row_top, 8.5, MUTED)
        grade = {"Good": "अच्छा", "Fair": "मध्यम", "Poor": "कम"}[factor.grade] if hindi else factor.grade
        line(grade, MARGIN + 435, row_top, 8.5, TEAL)
        pdf.setStrokeColor(LINE)
        pdf.line(MARGIN, HEIGHT - row_top - 4, WIDTH - MARGIN, HEIGHT - row_top - 4)

    cursor = quality_top + 95
    line("व्याख्या" if hindi else "Explanation", MARGIN, cursor, 12, TEAL, heavy=True)
    cursor = paragraph(explanation.summary, MARGIN, cursor + 7)
    method = result.parameters
    line("विधि और सीमाएँ" if hindi else "Method and limitations", MARGIN, cursor + 19, 12, TEAL, heavy=True)
    method_text = (f"वीवी की माध्यिका पर {method.speckle_radius_m} मीटर का फ़िल्टर लगाया गया। ग्रिड {method.scale_m} मीटर का है। बाद का संकेत "
                   f"{method.water_db:g} डेसीबल से कम और बदलाव {method.change_db:g} डेसीबल से कम होना चाहिए। पानी, भूभाग और छोटे समूह हटाए गए।"
                   if hindi else
                   f"Median VV, {method.speckle_radius_m} m filter on a {method.scale_m} m grid. Thresholds: post below {method.water_db:g} dB "
                   f"and change below {method.change_db:g} dB. Pre-existing water, terrain and groups under {method.min_cluster_pixels} pixels excluded.")
    cursor = paragraph(method_text, MARGIN, cursor + 25)
    cursor = paragraph(" ".join(explanation.limitations), MARGIN, cursor + 4, size=8.2, color=MUTED)
    cursor = paragraph(explanation.verification, MARGIN, cursor + 4, size=8.5, color=TEAL)

    footer = max(cursor + 10, 755)
    pdf.setStrokeColor(LINE)
    pdf.line(MARGIN, HEIGHT - footer, WIDTH - MARGIN, HEIGHT - footer)
    attribution = " ".join(result.attributions) + f"  |  {result.method_version}"
    footer = paragraph(attribution, MARGIN, footer + 6, size=7.4, color=MUTED)
    paragraph(("यह एक स्वचालित अनुमान है। क्षति की पुष्टि के लिए स्वतंत्र जाँच आवश्यक है।" if hindi else
               "Automated screening estimate. Damage requires independent field verification."),
              MARGIN, footer + 3, size=7.4, color=MUTED)
    pdf.showPage()
    pdf.save()
    return output.getvalue()


def build_report(result: AnalysisResult, layers: RenderedLayers, language: Language) -> bytes:
    # Font subsetting and shaping mutate ReportLab's font state across requests.
    if language == "hi":
        with _shape_lock:
            return _render(result, layers, language)
    return _render(result, layers, language)
