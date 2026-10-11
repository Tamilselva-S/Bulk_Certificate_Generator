"""
app/services/generator.py

PDF certificate generation using ReportLab.
Reproduces the KS Foundation academic certificate design with high visual fidelity.
"""

import math
import re
from datetime import date
from pathlib import Path

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.config import settings


# ── Color Palette ─────────────────────────────────────────────────────────────
NAVY_DARK    = colors.HexColor("#0D1B3D")  # Left panel and primary dark heading
NAVY_DEEP    = colors.HexColor("#060E20")  # Deep accent navy
GOLD_PRIMARY = colors.HexColor("#C9972D")  # Accent gold for borders, emblems, rules
GOLD_LIGHT   = colors.HexColor("#E5C36A")  # Highlights, inner borders, secondary stars
GOLD_BRIGHT  = colors.HexColor("#F9E59B")  # Bright gold accents
GOLD_DEEP    = colors.HexColor("#8A661C")  # Dark gold for labels, shadows
GOLD_BG_PILL = colors.HexColor("#FAF2DD")  # Pale gold pill fill for date badge
GOLD_DIVIDER = colors.HexColor("#DFCA98")  # Divider line tint
IVORY_CREAM  = colors.HexColor("#FCF8F1")  # Main certificate warm background
TEXT_DARK    = colors.HexColor("#15213C")  # Dark body text
TEXT_MUTED   = colors.HexColor("#64748B")  # Subtitle & supporting statement gray
WHITE        = colors.HexColor("#FFFFFF")


# ── Public API ────────────────────────────────────────────────────────────────

def generate_certificate_pdf(
    *,
    certificate_id: str,
    recipient_name: str,
    event_name: str,
    issuer: str,
    issue_date: date,
    output_dir: Path,
) -> Path:
    """
    Generate a PDF certificate and save it to `output_dir`.

    Parameters
    ----------
    certificate_id : str
        UUID of the Certificate record.
    recipient_name : str
        Full name of the recipient.
    event_name : str
        Name of the event or course.
    issuer : str
        Organisation issuing the certificate.
    issue_date : date
        Date to print on the certificate.
    output_dir : Path
        Directory where the PDF will be saved. Must already exist.

    Returns
    -------
    Path
        Absolute path of the generated PDF file.
    """
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    safe_filename = _safe_filename(certificate_id) + ".pdf"
    output_path = (output_dir / safe_filename).resolve()

    if not str(output_path).startswith(str(output_dir)):
        raise ValueError(
            f"Resolved output path {output_path} is outside the "
            f"configured output directory {output_dir}."
        )

    _draw_certificate(
        output_path=output_path,
        certificate_id=certificate_id,
        recipient_name=recipient_name,
        event_name=event_name,
        issuer=issuer,
        issue_date=issue_date,
    )

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise OSError(f"PDF was not created at {output_path} or is empty.")

    return output_path


# ── Internal helpers ──────────────────────────────────────────────────────────

def _safe_filename(raw: str) -> str:
    """Strip anything that is not alphanumeric or a hyphen from the string."""
    return re.sub(r"[^A-Za-z0-9\-]", "_", raw)


def _truncate_text(text: str, max_chars: int) -> str:
    """Return text truncated to max_chars with '…' if it was longer."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


# ── Drawing Primitives & Vector Ornaments ─────────────────────────────────────

def _draw_diamond(
    c: canvas.Canvas,
    cx: float,
    cy: float,
    size: float,
    fill_color: colors.Color = GOLD_PRIMARY,
    stroke_color: colors.Color | None = None,
) -> None:
    """Draw a rotated diamond (square turned 45 degrees) centered at (cx, cy)."""
    c.saveState()
    half = size / 2.0
    p = c.beginPath()
    p.moveTo(cx, cy + half)
    p.lineTo(cx + half, cy)
    p.lineTo(cx, cy - half)
    p.lineTo(cx - half, cy)
    p.close()
    c.setFillColor(fill_color)
    if stroke_color:
        c.setStrokeColor(stroke_color)
        c.setLineWidth(0.5)
        c.drawPath(p, fill=1, stroke=1)
    else:
        c.drawPath(p, fill=1, stroke=0)
    c.restoreState()


def _draw_star_shape(
    c: canvas.Canvas,
    cx: float,
    cy: float,
    r_outer: float,
    r_inner: float,
    points: int = 5,
    fill_color: colors.Color = GOLD_PRIMARY,
) -> None:
    """Draw a 5-pointed star polygon centered at (cx, cy)."""
    c.saveState()
    p = c.beginPath()
    angle_step = math.pi / points
    start_angle = math.pi / 2.0  # Pointing up

    for i in range(points * 2):
        r = r_outer if i % 2 == 0 else r_inner
        ang = start_angle + i * angle_step
        x = cx + r * math.cos(ang)
        y = cy + r * math.sin(ang)
        if i == 0:
            p.moveTo(x, y)
        else:
            p.lineTo(x, y)
    p.close()
    c.setFillColor(fill_color)
    c.drawPath(p, fill=1, stroke=0)
    c.restoreState()


def _draw_panel_corner_decorations(
    c: canvas.Canvas,
    panel_w: float,
    page_h: float,
) -> None:
    """Draw subtle curved gold line decorations in the corners of the left panel."""
    c.saveState()
    c.setStrokeColor(GOLD_PRIMARY)
    c.setLineWidth(0.5)

    # Concentric curved quarter-circles in top-left
    for r in (10 * mm, 17 * mm, 24 * mm):
        c.arc(-r, page_h - r, r, page_h + r, 270, 90)

    # Concentric curved quarter-circles in bottom-left
    for r in (10 * mm, 17 * mm, 24 * mm):
        c.arc(-r, -r, r, r, 0, 90)

    # Subtle quarter-circle arcs near top-right edge
    right_x = panel_w - 1.5 * mm
    for r in (8 * mm, 14 * mm):
        c.arc(right_x - r, page_h - r, right_x + r, page_h + r, 180, 90)

    # Subtle quarter-circle arcs near bottom-right edge
    for r in (8 * mm, 14 * mm):
        c.arc(right_x - r, -r, right_x + r, r, 90, 90)

    c.restoreState()


def _draw_graduation_cap(
    c: canvas.Canvas,
    cx: float,
    cy: float,
    width: float,
    color: colors.Color = GOLD_PRIMARY,
) -> None:
    """Draw a vector graduation cap (mortarboard) centered at (cx, cy)."""
    c.saveState()
    c.setFillColor(color)
    c.setStrokeColor(color)
    c.setLineWidth(0.5)

    half_w = width / 2.0
    half_h = width * 0.28

    # Top rhombus (diamond cap)
    top_p = c.beginPath()
    top_p.moveTo(cx, cy + half_h)
    top_p.lineTo(cx + half_w, cy)
    top_p.lineTo(cx, cy - half_h)
    top_p.lineTo(cx - half_w, cy)
    top_p.close()
    c.drawPath(top_p, fill=1, stroke=1)

    # Skullcap underneath
    cap_w = half_w * 0.55
    cap_h = half_h * 0.95
    under_p = c.beginPath()
    under_p.moveTo(cx - cap_w, cy - half_h * 0.2)
    under_p.lineTo(cx + cap_w, cy - half_h * 0.2)
    under_p.lineTo(cx + cap_w * 0.8, cy - half_h * 0.2 - cap_h)
    under_p.curveTo(
        cx + cap_w * 0.4, cy - half_h * 0.2 - cap_h * 1.3,
        cx - cap_w * 0.4, cy - half_h * 0.2 - cap_h * 1.3,
        cx - cap_w * 0.8, cy - half_h * 0.2 - cap_h,
    )
    under_p.close()
    c.drawPath(under_p, fill=1, stroke=0)

    # Center button dot
    c.setFillColor(GOLD_LIGHT)
    c.circle(cx, cy, width * 0.05, fill=1, stroke=0)

    # Tassel string and fringe hanging to the right
    tassel = c.beginPath()
    tassel.moveTo(cx, cy)
    tassel.lineTo(cx + half_w * 0.85, cy - half_h * 0.4)
    tassel.lineTo(cx + half_w * 0.95, cy - half_h * 1.45)
    c.setStrokeColor(GOLD_LIGHT)
    c.setLineWidth(0.8)
    c.drawPath(tassel, fill=0, stroke=1)

    # Tassel fringe brush
    c.setFillColor(GOLD_LIGHT)
    c.circle(cx + half_w * 0.95, cy - half_h * 1.5, width * 0.045, fill=1, stroke=0)

    c.restoreState()


def _draw_laurel_branch(
    c: canvas.Canvas,
    cx: float,
    cy: float,
    radius: float,
    is_left: bool = True,
    leaf_color: colors.Color = GOLD_PRIMARY,
) -> None:
    """Draw one curved laurel wreath branch with pairs of leaves."""
    c.saveState()
    c.setFillColor(leaf_color)
    c.setStrokeColor(leaf_color)
    c.setLineWidth(0.6)

    sign = -1.0 if is_left else 1.0
    stem = c.beginPath()
    stem.moveTo(cx + sign * 2.5 * mm, cy - radius * 0.7)
    stem.curveTo(
        cx + sign * radius * 0.95, cy - radius * 0.4,
        cx + sign * radius * 0.95, cy + radius * 0.4,
        cx + sign * 2.5 * mm, cy + radius * 0.75,
    )
    c.drawPath(stem, fill=0, stroke=1)

    num_pairs = 6
    for i in range(num_pairs):
        t = (i + 0.5) / num_pairs
        ang = -math.pi * 0.35 + t * (math.pi * 0.7)
        dist = radius * 0.78
        lx = cx + sign * dist * math.cos(ang)
        ly = cy + dist * math.sin(ang)

        c.saveState()
        c.translate(lx, ly)
        rot = (ang * 180.0 / math.pi) if is_left else (180 - ang * 180.0 / math.pi)
        c.rotate(rot + (25 if is_left else -25))

        leaf_p = c.beginPath()
        leaf_p.moveTo(0, 0)
        leaf_p.curveTo(1.5 * mm, 0.7 * mm, 2.5 * mm, 0.5 * mm, 3.2 * mm, 0)
        leaf_p.curveTo(2.5 * mm, -0.5 * mm, 1.5 * mm, -0.7 * mm, 0, 0)
        leaf_p.close()
        c.drawPath(leaf_p, fill=1, stroke=0)
        c.restoreState()

    c.restoreState()


def _draw_panel_emblem(
    c: canvas.Canvas,
    cx: float,
    cy: float,
) -> None:
    """
    Draw the circular gold emblem in the middle of the left navy panel.

    Requirements:
      - Circular gold emblem
      - Graduation cap
      - Laurel wreath
      - Words: LEARN, GROW, ACHIEVE
      - Three small gold stars
    """
    c.saveState()
    r_outer = 20.0 * mm
    r_inner = 18.0 * mm

    # Outer double gold rings
    c.setStrokeColor(GOLD_PRIMARY)
    c.setLineWidth(1.6)
    c.circle(cx, cy, r_outer, stroke=1, fill=0)

    c.setStrokeColor(GOLD_LIGHT)
    c.setLineWidth(0.8)
    c.circle(cx, cy, r_inner, stroke=1, fill=0)

    # Concentric beaded gold pearls
    num_dots = 28
    for i in range(num_dots):
        ang = i * (2.0 * math.pi / num_dots)
        bx = cx + (r_inner - 1.2 * mm) * math.cos(ang)
        by = cy + (r_inner - 1.2 * mm) * math.sin(ang)
        c.setFillColor(GOLD_PRIMARY)
        c.circle(bx, by, 0.3 * mm, fill=1, stroke=0)

    # 3 Gold Stars at the top
    star_y = cy + 11.5 * mm
    _draw_star_shape(c, cx - 6.0 * mm, star_y - 0.7 * mm, 1.5 * mm, 0.7 * mm, points=5, fill_color=GOLD_LIGHT)
    _draw_star_shape(c, cx, star_y + 0.4 * mm, 2.2 * mm, 1.0 * mm, points=5, fill_color=GOLD_PRIMARY)
    _draw_star_shape(c, cx + 6.0 * mm, star_y - 0.7 * mm, 1.5 * mm, 0.7 * mm, points=5, fill_color=GOLD_LIGHT)

    # Laurel Wreath left and right
    _draw_laurel_branch(c, cx, cy + 0.5 * mm, radius=13.5 * mm, is_left=True, leaf_color=GOLD_LIGHT)
    _draw_laurel_branch(c, cx, cy + 0.5 * mm, radius=13.5 * mm, is_left=False, leaf_color=GOLD_LIGHT)

    # Graduation Cap in the center
    _draw_graduation_cap(c, cx, cy + 2.5 * mm, width=13.0 * mm, color=GOLD_PRIMARY)

    # Horizontal gold ribbon banner for words LEARN • GROW • ACHIEVE
    banner_w = 26.0 * mm
    banner_h = 5.0 * mm
    bx = cx - banner_w / 2.0
    by = cy - 9.5 * mm

    c.setFillColor(NAVY_DARK)
    c.setStrokeColor(GOLD_PRIMARY)
    c.setLineWidth(0.75)
    c.roundRect(bx, by, banner_w, banner_h, 1.5 * mm, fill=1, stroke=1)

    c.setFillColor(GOLD_LIGHT)
    c.setFont("Helvetica-Bold", 4.9)
    c.drawCentredString(cx, by + 1.4 * mm, "LEARN  \u2022  GROW  \u2022  ACHIEVE")

    c.restoreState()


def _draw_decorative_border_and_corners(
    c: canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
) -> None:
    """
    Draw a classic academic certificate border with gold double-lines
    and corner ornamental diamond flourishes in the main content area.
    """
    c.saveState()

    # Outer primary gold border
    c.setStrokeColor(GOLD_PRIMARY)
    c.setLineWidth(1.2)
    c.rect(x, y, w, h, fill=0, stroke=1)

    # Inner light gold border
    inset = 2.4 * mm
    ix = x + inset
    iy = y + inset
    iw = w - 2 * inset
    ih = h - 2 * inset
    c.setStrokeColor(GOLD_LIGHT)
    c.setLineWidth(0.6)
    c.rect(ix, iy, iw, ih, fill=0, stroke=1)

    # Four corner ornamental diamond accents & flourishes
    corner_coords = [
        (ix, iy),            # Bottom-left
        (ix + iw, iy),       # Bottom-right
        (ix, iy + ih),       # Top-left
        (ix + iw, iy + ih),  # Top-right
    ]

    for cx_cor, cy_cor in corner_coords:
        # Central corner diamond
        _draw_diamond(c, cx_cor, cy_cor, 4.0 * mm, fill_color=GOLD_PRIMARY, stroke_color=GOLD_LIGHT)
        # Inner white dot
        c.setFillColor(WHITE)
        c.circle(cx_cor, cy_cor, 0.45 * mm, fill=1, stroke=0)

    # Subtle compact corner bracket accents (3.5 mm)
    b_len = 3.5 * mm
    c.setStrokeColor(GOLD_PRIMARY)
    c.setLineWidth(0.6)

    # Bottom-left bracket
    c.line(ix + 2.0 * mm, iy + 2.0 * mm, ix + 2.0 * mm + b_len, iy + 2.0 * mm)
    c.line(ix + 2.0 * mm, iy + 2.0 * mm, ix + 2.0 * mm, iy + 2.0 * mm + b_len)

    # Bottom-right bracket
    c.line(ix + iw - 2.0 * mm, iy + 2.0 * mm, ix + iw - 2.0 * mm - b_len, iy + 2.0 * mm)
    c.line(ix + iw - 2.0 * mm, iy + 2.0 * mm, ix + iw - 2.0 * mm, iy + 2.0 * mm + b_len)

    # Top-left bracket
    c.line(ix + 2.0 * mm, iy + ih - 2.0 * mm, ix + 2.0 * mm + b_len, iy + ih - 2.0 * mm)
    c.line(ix + 2.0 * mm, iy + ih - 2.0 * mm, ix + 2.0 * mm, iy + ih - 2.0 * mm - b_len)

    # Top-right bracket
    c.line(ix + iw - 2.0 * mm, iy + ih - 2.0 * mm, ix + iw - 2.0 * mm - b_len, iy + ih - 2.0 * mm)
    c.line(ix + iw - 2.0 * mm, iy + ih - 2.0 * mm, ix + iw - 2.0 * mm, iy + ih - 2.0 * mm - b_len)

    c.restoreState()


def _draw_horizontal_divider_with_diamond(
    c: canvas.Canvas,
    cx: float,
    y: float,
    total_width: float,
    line_color: colors.Color = GOLD_PRIMARY,
    diamond_size: float = 3.6 * mm,
) -> None:
    """Draw a thin gold horizontal line interrupted by a center diamond ornament."""
    c.saveState()
    half_w = total_width / 2.0
    gap = diamond_size * 0.9

    c.setStrokeColor(line_color)
    c.setLineWidth(0.8)

    # Left line segment
    c.line(cx - half_w, y, cx - gap, y)
    # Right line segment
    c.line(cx + gap, y, cx + half_w, y)

    # Central diamond ornament
    _draw_diamond(c, cx, y, diamond_size, fill_color=line_color)
    # Flanking accent dots
    c.setFillColor(line_color)
    c.circle(cx - gap * 0.55, y, 0.45 * mm, fill=1, stroke=0)
    c.circle(cx + gap * 0.55, y, 0.45 * mm, fill=1, stroke=0)

    c.restoreState()


def _draw_date_badge(
    c: canvas.Canvas,
    cx: float,
    cy: float,
    date_text: str,
) -> None:
    """
    Draw a rounded pale-gold date label with a mini calendar icon.
    Example text: 'Issued on 11 October 2026'
    """
    c.saveState()

    font_name = "Helvetica-Bold"
    font_size = 8.5
    text_width = c.stringWidth(date_text, font_name, font_size)

    icon_w = 4.2 * mm
    pad_h = 4.5 * mm
    pad_w = 5.0 * mm

    total_w = text_width + icon_w + pad_w * 2 + 2.5 * mm
    total_h = 7.2 * mm
    rx = cx - total_w / 2.0
    ry = cy - total_h / 2.0

    # Rounded pale gold pill badge
    c.setFillColor(GOLD_BG_PILL)
    c.setStrokeColor(GOLD_PRIMARY)
    c.setLineWidth(0.8)
    c.roundRect(rx, ry, total_w, total_h, total_h / 2.0, fill=1, stroke=1)

    # Mini vector calendar icon
    icon_x = rx + pad_w
    icon_y = cy - 1.8 * mm
    cal_w = 3.6 * mm
    cal_h = 3.6 * mm

    # Calendar base
    c.setFillColor(WHITE)
    c.setStrokeColor(GOLD_DEEP)
    c.setLineWidth(0.6)
    c.rect(icon_x, icon_y, cal_w, cal_h, fill=1, stroke=1)

    # Calendar header band
    c.setFillColor(GOLD_PRIMARY)
    c.rect(icon_x, icon_y + cal_h - 1.0 * mm, cal_w, 1.0 * mm, fill=1, stroke=0)

    # Calendar hanger tabs
    c.setFillColor(GOLD_DEEP)
    c.rect(icon_x + 0.7 * mm, icon_y + cal_h, 0.6 * mm, 0.6 * mm, fill=1, stroke=0)
    c.rect(icon_x + cal_w - 1.3 * mm, icon_y + cal_h, 0.6 * mm, 0.6 * mm, fill=1, stroke=0)

    # Calendar grid dots
    c.setFillColor(GOLD_DEEP)
    c.circle(icon_x + 1.2 * mm, icon_y + 1.5 * mm, 0.25 * mm, fill=1, stroke=0)
    c.circle(icon_x + 2.4 * mm, icon_y + 1.5 * mm, 0.25 * mm, fill=1, stroke=0)
    c.circle(icon_x + 1.2 * mm, icon_y + 0.7 * mm, 0.25 * mm, fill=1, stroke=0)
    c.circle(icon_x + 2.4 * mm, icon_y + 0.7 * mm, 0.25 * mm, fill=1, stroke=0)

    # Date text
    c.setFillColor(GOLD_DEEP)
    c.setFont(font_name, font_size)
    text_x = icon_x + cal_w + 2.5 * mm
    c.drawString(text_x, cy - 1.1 * mm, date_text)

    c.restoreState()


def _draw_executive_signature(
    c: canvas.Canvas,
    cx: float,
    baseline_y: float,
) -> None:
    """
    Draw an authentic, flowing executive cursive vector signature
    above the signature line.
    """
    c.saveState()
    c.setStrokeColor(NAVY_DARK)
    c.setLineWidth(1.3)
    c.setLineCap(1)  # Round cap
    c.setLineJoin(1) # Round join

    # Start signature relative to (cx, baseline_y)
    sx = cx - 22 * mm
    sy = baseline_y + 2 * mm

    # Initial flourish & capital 'S'
    p = c.beginPath()
    p.moveTo(sx, sy + 3 * mm)
    p.curveTo(sx + 2 * mm, sy + 13 * mm, sx + 7 * mm, sy + 15 * mm, sx + 8 * mm, sy + 10 * mm)
    p.curveTo(sx + 8.5 * mm, sy + 5 * mm, sx + 2 * mm, sy + 4 * mm, sx + 5 * mm, sy + 1 * mm)
    p.curveTo(sx + 7 * mm, sy - 1 * mm, sx + 12 * mm, sy + 2 * mm, sx + 14 * mm, sy + 6 * mm)

    c.drawPath(p, fill=0, stroke=1)
    c.setFillColor(NAVY_DARK)
    c.circle(sx + 15.5 * mm, sy + 1.5 * mm, 0.6 * mm, fill=1, stroke=0)

    # Flowing cursive 'Srinivasan'
    p2 = c.beginPath()
    sx2 = sx + 18 * mm
    p2.moveTo(sx2, sy + 2 * mm)
    p2.curveTo(sx2 + 1 * mm, sy + 9 * mm, sx2 + 4 * mm, sy + 11 * mm, sx2 + 5 * mm, sy + 7 * mm)
    p2.curveTo(sx2 + 5.5 * mm, sy + 3 * mm, sx2 + 1 * mm, sy + 2 * mm, sx2 + 3 * mm, sy + 1 * mm)
    p2.curveTo(sx2 + 5 * mm, sy + 2 * mm, sx2 + 7 * mm, sy + 4 * mm, sx2 + 8 * mm, sy + 2 * mm)
    p2.curveTo(sx2 + 9 * mm, sy + 4.5 * mm, sx2 + 11 * mm, sy + 4.5 * mm, sx2 + 12 * mm, sy + 1.5 * mm)
    p2.curveTo(sx2 + 13 * mm, sy + 4 * mm, sx2 + 15 * mm, sy + 4 * mm, sx2 + 16 * mm, sy + 1.5 * mm)
    p2.curveTo(sx2 + 17 * mm, sy + 5 * mm, sx2 + 19 * mm, sy + 5 * mm, sx2 + 20 * mm, sy + 1.5 * mm)
    p2.curveTo(sx2 + 21 * mm, sy + 4 * mm, sx2 + 23 * mm, sy + 4 * mm, sx2 + 24 * mm, sy + 1.5 * mm)
    p2.curveTo(sx2 + 25 * mm, sy + 5 * mm, sx2 + 27 * mm, sy + 5 * mm, sx2 + 28 * mm, sy + 2 * mm)

    # Underline flourish
    p2.curveTo(sx2 + 31 * mm, sy + 6 * mm, sx2 + 33 * mm, sy + 2 * mm, sx2 + 28 * mm, sy - 2 * mm)
    p2.curveTo(sx2 + 20 * mm, sy - 4 * mm, sx2 + 6 * mm, sy - 3 * mm, sx2 - 2 * mm, sy - 2.5 * mm)
    p2.curveTo(sx2 - 5 * mm, sy - 2 * mm, sx2 - 1 * mm, sy - 1 * mm, sx2 + 4 * mm, sy - 1.5 * mm)
    c.drawPath(p2, fill=0, stroke=1)

    c.restoreState()


def _draw_award_seal(
    c: canvas.Canvas,
    cx: float,
    cy: float,
    radius: float = 14.5 * mm,
) -> None:
    """
    Draw a circular embossed-looking gold award seal in the lower-center area.

    Requirements:
      - Circular embossed-looking gold seal
      - Graduation-cap icon
      - Laurel wreath
      - Layered gold circles and scalloped edges to create a realistic award-seal appearance
    """
    c.saveState()

    # 1. Hanging Ribbon Tails at the bottom
    ribbon_w = 6.0 * mm
    ribbon_len = 13.0 * mm
    c.setFillColor(GOLD_DEEP)
    c.setStrokeColor(colors.HexColor("#6B4F12"))
    c.setLineWidth(0.5)

    # Left ribbon tail (angled left)
    rib_l = c.beginPath()
    rib_l.moveTo(cx - 2.0 * mm, cy - radius * 0.4)
    rib_l.lineTo(cx - 9.0 * mm, cy - radius * 0.4 - ribbon_len)
    rib_l.lineTo(cx - 5.0 * mm, cy - radius * 0.4 - ribbon_len + 3.0 * mm)  # V-notch
    rib_l.lineTo(cx - 1.0 * mm, cy - radius * 0.4 - ribbon_len)
    rib_l.lineTo(cx + 1.0 * mm, cy - radius * 0.4)
    rib_l.close()
    c.drawPath(rib_l, fill=1, stroke=1)

    # Right ribbon tail (angled right)
    c.setFillColor(GOLD_PRIMARY)
    rib_r = c.beginPath()
    rib_r.moveTo(cx - 1.0 * mm, cy - radius * 0.4)
    rib_r.lineTo(cx + 1.0 * mm, cy - radius * 0.4 - ribbon_len)
    rib_r.lineTo(cx + 5.0 * mm, cy - radius * 0.4 - ribbon_len + 3.0 * mm)  # V-notch
    rib_r.lineTo(cx + 9.0 * mm, cy - radius * 0.4 - ribbon_len)
    rib_r.lineTo(cx + 2.0 * mm, cy - radius * 0.4)
    rib_r.close()
    c.drawPath(rib_r, fill=1, stroke=1)

    # 2. Scalloped Rosette Edge (36 teeth)
    num_teeth = 36
    r_outer = radius
    r_inner = radius - 1.4 * mm
    rosette = c.beginPath()
    for i in range(num_teeth * 2):
        angle = i * (math.pi / num_teeth)
        r = r_outer if i % 2 == 0 else r_inner
        x = cx + r * math.cos(angle)
        y = cy + r * math.sin(angle)
        if i == 0:
            rosette.moveTo(x, y)
        else:
            rosette.lineTo(x, y)
    rosette.close()

    c.setFillColor(GOLD_PRIMARY)
    c.setStrokeColor(colors.HexColor("#A87A18"))
    c.setLineWidth(0.8)
    c.drawPath(rosette, fill=1, stroke=1)

    # 3. Layered Concentric Gold Circles for 3D Embossed Effect
    c.setFillColor(GOLD_LIGHT)
    c.setStrokeColor(GOLD_PRIMARY)
    c.setLineWidth(0.9)
    c.circle(cx, cy, radius - 2.0 * mm, fill=1, stroke=1)

    c.setFillColor(colors.HexColor("#FAF2DB"))
    c.setStrokeColor(GOLD_DEEP)
    c.setLineWidth(0.6)
    c.circle(cx, cy, radius - 3.4 * mm, fill=1, stroke=1)

    # Beaded pearl ring
    num_beads = 28
    bead_r = radius - 4.4 * mm
    c.setFillColor(GOLD_DEEP)
    for i in range(num_beads):
        ang = i * (2.0 * math.pi / num_beads)
        bx = cx + bead_r * math.cos(ang)
        by = cy + bead_r * math.sin(ang)
        c.circle(bx, by, 0.3 * mm, fill=1, stroke=0)

    # Inner medallion disc
    medallion_r = radius - 5.5 * mm
    c.setFillColor(GOLD_PRIMARY)
    c.setStrokeColor(GOLD_LIGHT)
    c.setLineWidth(0.7)
    c.circle(cx, cy, medallion_r, fill=1, stroke=1)

    # Innermost ivory/cream medal surface
    core_r = radius - 6.5 * mm
    c.setFillColor(colors.HexColor("#FFFDF9"))
    c.circle(cx, cy, core_r, fill=1, stroke=0)

    # 4. Center Graduation Cap & Laurel Wreath inside Seal
    _draw_laurel_branch(c, cx, cy, radius=core_r * 0.95, is_left=True, leaf_color=GOLD_PRIMARY)
    _draw_laurel_branch(c, cx, cy, radius=core_r * 0.95, is_left=False, leaf_color=GOLD_PRIMARY)
    _draw_graduation_cap(c, cx, cy + 0.6 * mm, width=7.5 * mm, color=GOLD_DEEP)

    # Small gold star below cap
    _draw_star_shape(c, cx, cy - 3.4 * mm, 1.1 * mm, 0.45 * mm, points=5, fill_color=GOLD_PRIMARY)

    c.restoreState()


def _draw_shield_icon(
    c: canvas.Canvas,
    cx: float,
    cy: float,
    size: float = 4.8 * mm,
) -> None:
    """Draw a vector shield verification icon with a checkmark."""
    c.saveState()
    half_w = size * 0.5
    top_y = cy + size * 0.5
    bot_y = cy - size * 0.5

    # Shield polygon
    shield = c.beginPath()
    shield.moveTo(cx - half_w, top_y)
    shield.lineTo(cx + half_w, top_y)
    shield.curveTo(
        cx + half_w, cy - size * 0.1,
        cx + half_w * 0.6, bot_y + size * 0.2,
        cx, bot_y,
    )
    shield.curveTo(
        cx - half_w * 0.6, bot_y + size * 0.2,
        cx - half_w, cy - size * 0.1,
        cx - half_w, top_y,
    )
    shield.close()

    c.setFillColor(colors.HexColor("#ECFDF5"))
    c.setStrokeColor(colors.HexColor("#059669"))
    c.setLineWidth(0.75)
    c.drawPath(shield, fill=1, stroke=1)

    # Checkmark inside shield
    check = c.beginPath()
    check.moveTo(cx - half_w * 0.45, cy)
    check.lineTo(cx - half_w * 0.1, cy - size * 0.22)
    check.lineTo(cx + half_w * 0.5, cy + size * 0.22)
    c.setStrokeColor(colors.HexColor("#059669"))
    c.setLineWidth(0.9)
    c.setLineCap(1)
    c.drawPath(check, fill=0, stroke=1)

    c.restoreState()


def _draw_tracked_centred_string(
    c: canvas.Canvas,
    cx: float,
    cy: float,
    text: str,
    font_name: str,
    font_size: float,
    char_space: float = 1.0,
    fill_color: colors.Color = GOLD_PRIMARY,
) -> None:
    """Draw text centered horizontally with character spacing."""
    c.saveState()
    c.setFillColor(fill_color)
    t = c.beginText()
    t.setFont(font_name, font_size)
    t.setCharSpace(char_space)
    t.setFillColor(fill_color)
    w = c.stringWidth(text, font_name, font_size) + max(0, len(text) - 1) * char_space
    t.setTextOrigin(cx - w / 2.0, cy)
    t.textOut(text)
    c.drawText(t)
    c.restoreState()


# ── Core Certificate Renderer ─────────────────────────────────────────────────

def _draw_certificate(
    *,
    output_path: Path,
    certificate_id: str,
    recipient_name: str,
    event_name: str,
    issuer: str,
    issue_date: date,
) -> None:
    """
    Render the certificate with exact layout, proportions, colors,
    and decorative elements matching the KS Foundation reference design.
    """
    page_w, page_h = landscape(A4)  # 297mm x 210mm (841.89 pt x 595.28 pt)
    c = canvas.Canvas(str(output_path), pagesize=landscape(A4))

    # ──────────────────────────────────────────────────────────────────────────
    # 1. Left Navy-Blue Branding Panel (~24% of page width)
    # ──────────────────────────────────────────────────────────────────────────
    panel_w = round(page_w * 0.24, 2)  # ~71.25 mm (202.05 pt)
    panel_cx = (panel_w - 1.5 * mm) / 2.0

    # Navy background
    c.setFillColor(NAVY_DARK)
    c.rect(0, 0, panel_w, page_h, fill=1, stroke=0)

    # Narrow vertical gold separator along right edge
    c.setFillColor(GOLD_PRIMARY)
    c.rect(panel_w - 1.5 * mm, 0, 1.5 * mm, page_h, fill=1, stroke=0)

    # Subtle curved gold line decorations in corners of panel
    _draw_panel_corner_decorations(c, panel_w, page_h)

    # ── Top Branding Section ──
    # Large gold serif letters: KS
    c.setFillColor(GOLD_PRIMARY)
    c.setFont("Times-Bold", 42)
    c.drawCentredString(panel_cx, page_h - 38 * mm, "KS")

    # "FOUNDATION" in white uppercase letters
    _draw_tracked_centred_string(
        c,
        cx=panel_cx,
        cy=page_h - 45.5 * mm,
        text="FOUNDATION",
        font_name="Helvetica-Bold",
        font_size=8.0,
        char_space=1.0,
        fill_color=WHITE,
    )

    # Thin gold horizontal divider with small central diamond
    _draw_horizontal_divider_with_diamond(
        c, cx=panel_cx, y=page_h - 49.5 * mm, total_width=32 * mm, line_color=GOLD_PRIMARY, diamond_size=2.4 * mm
    )

    # "Excellence in Education" in smaller white text
    c.setFillColor(colors.HexColor("#D1D5DB"))
    c.setFont("Helvetica-Oblique", 7.0)
    c.drawCentredString(panel_cx, page_h - 54.5 * mm, "Excellence in Education")

    # ── Middle Emblem Section ──
    # Circular gold emblem with cap, wreath, LEARN GROW ACHIEVE, 3 stars
    emblem_cy = page_h / 2.0 + 3.0 * mm
    _draw_panel_emblem(c, cx=panel_cx, cy=emblem_cy)

    # ── Bottom QR Code Container ──
    # White QR-code container with black QR code and label "SCAN TO VERIFY"
    qr_size = 23.5 * mm
    qr_container_w = qr_size + 6.0 * mm
    qr_container_h = qr_size + 6.0 * mm
    qr_container_x = panel_cx - (qr_container_w / 2.0)
    qr_container_y = 20.0 * mm

    c.setFillColor(WHITE)
    c.setStrokeColor(GOLD_PRIMARY)
    c.setLineWidth(0.6)
    c.roundRect(
        qr_container_x, qr_container_y,
        qr_container_w, qr_container_h,
        2.5 * mm, fill=1, stroke=1
    )

    # Generate QR Code for live verification URL
    base_url = getattr(settings, "BASE_URL", "http://127.0.0.1:8000").rstrip("/")
    verify_url = f"{base_url}/verify/{certificate_id}"

    qr_widget = QrCodeWidget(verify_url)
    bounds = qr_widget.getBounds()
    qw = bounds[2] - bounds[0]
    qh = bounds[3] - bounds[1]
    qr_drawing = Drawing(
        qr_size, qr_size,
        transform=[qr_size / qw, 0, 0, qr_size / qh, 0, 0],
    )
    qr_drawing.add(qr_widget)
    renderPDF.draw(qr_drawing, c, qr_container_x + 3.0 * mm, qr_container_y + 3.0 * mm)

    # Label below QR container: "SCAN TO VERIFY"
    c.setFillColor(WHITE)
    c.setFont("Helvetica-Bold", 6.8)
    c.drawCentredString(panel_cx, qr_container_y - 5.5 * mm, "SCAN TO VERIFY")

    # ──────────────────────────────────────────────────────────────────────────
    # 2. Main Certificate Content Area (Remaining ~76% of page width)
    # ──────────────────────────────────────────────────────────────────────────
    content_x = panel_w
    content_w = page_w - panel_w
    content_cx = content_x + (content_w / 2.0)

    # Warm ivory / cream background
    c.setFillColor(IVORY_CREAM)
    c.rect(content_x, 0, content_w, page_h, fill=1, stroke=0)

    # Decorative thin gold borders and corner ornaments
    margin = 8.0 * mm
    border_x = content_x + margin
    border_y = margin
    border_w = content_w - (margin * 2.0)
    border_h = page_h - (margin * 2.0)
    _draw_decorative_border_and_corners(c, border_x, border_y, border_w, border_h)

    # ── Content Hierarchy & Vertical Positioning ──

    # 1. Small gold uppercase heading with letter spacing
    _draw_tracked_centred_string(
        c,
        cx=content_cx,
        cy=page_h - 26.0 * mm,
        text="CERTIFICATE OF ACHIEVEMENT",
        font_name="Helvetica-Bold",
        font_size=9.0,
        char_space=1.2,
        fill_color=GOLD_PRIMARY,
    )

    # 2. Large, bold, dark navy serif heading: "Certificate"
    c.setFillColor(NAVY_DARK)
    c.setFont("Times-Bold", 38)
    c.drawCentredString(content_cx, page_h - 41.0 * mm, "Certificate")

    # 3. Elegant gold italic subtitle: "of Completion"
    c.setFillColor(GOLD_PRIMARY)
    c.setFont("Times-Italic", 20)
    c.drawCentredString(content_cx, page_h - 51.0 * mm, "of Completion")

    # 4. Thin gold horizontal divider with small central diamond ornament
    _draw_horizontal_divider_with_diamond(
        c,
        cx=content_cx,
        y=page_h - 57.0 * mm,
        total_width=140.0 * mm,
        line_color=GOLD_PRIMARY,
        diamond_size=3.4 * mm,
    )

    # 5. Italic introductory text
    c.setFillColor(TEXT_MUTED)
    c.setFont("Times-Italic", 11.5)
    c.drawCentredString(
        content_cx,
        page_h - 67.0 * mm,
        "This certificate is proudly presented to",
    )

    # 6. Large, bold, dark navy recipient name
    name_y = page_h - 82.0 * mm
    raw_name = recipient_name.strip()

    # Dynamic scaling for long recipient names to prevent overflow/clipping
    max_name_w = content_w - 44.0 * mm
    name_font_size = 29.0
    measured_name_w = c.stringWidth(raw_name, "Times-Bold", name_font_size)
    if measured_name_w > max_name_w:
        name_font_size = max(16.0, name_font_size * (max_name_w / measured_name_w))
        display_name = raw_name
    else:
        display_name = raw_name

    c.setFillColor(NAVY_DARK)
    c.setFont("Times-Bold", name_font_size)
    c.drawCentredString(content_cx, name_y, display_name)

    # 7. Thin gold horizontal line below the recipient name
    name_line_w = min(max_name_w, max(65.0 * mm, c.stringWidth(display_name, "Times-Bold", name_font_size) + 12.0 * mm))
    c.setStrokeColor(GOLD_PRIMARY)
    c.setLineWidth(1.2)
    c.line(
        content_cx - name_line_w / 2.0, name_y - 3.5 * mm,
        content_cx + name_line_w / 2.0, name_y - 3.5 * mm
    )

    # 8. Completion description
    c.setFillColor(TEXT_MUTED)
    c.setFont("Times-Roman", 10.5)
    c.drawCentredString(
        content_cx,
        page_h - 96.5 * mm,
        "For successfully completing the",
    )

    # 9. Large, bold course title
    course_y = page_h - 107.5 * mm
    raw_event = event_name.strip()
    max_event_w = content_w - 40.0 * mm
    event_font_size = 17.0
    measured_event_w = c.stringWidth(raw_event, "Helvetica-Bold", event_font_size)
    if measured_event_w > max_event_w:
        event_font_size = max(12.0, event_font_size * (max_event_w / measured_event_w))

    c.setFillColor(TEXT_DARK)
    c.setFont("Helvetica-Bold", event_font_size)
    c.drawCentredString(content_cx, course_y, raw_event)

    # 10. Supporting statement on two lines
    c.setFillColor(TEXT_MUTED)
    c.setFont("Helvetica", 9.0)
    c.drawCentredString(
        content_cx,
        page_h - 117.5 * mm,
        "We appreciate your dedication, effort, and commitment",
    )
    c.drawCentredString(
        content_cx,
        page_h - 122.5 * mm,
        "towards enhancing your skills and knowledge.",
    )

    # 11. Rounded pale-gold date label with calendar icon
    date_str = f"Issued on {issue_date.strftime('%d %B %Y')}"
    _draw_date_badge(c, cx=content_cx, cy=page_h - 134.0 * mm, date_text=date_str)

    # ──────────────────────────────────────────────────────────────────────────
    # 3. Bottom Signature and Verification Section
    # ──────────────────────────────────────────────────────────────────────────
    # Three cleanly separated non-overlapping columns:
    #   - Left: Signature of S. Srinivasan, Director
    #   - Center: Scalloped embossed circular gold award seal
    #   - Right: Certificate ID, shield verification icon, URL

    # Center Gold Award Seal
    seal_cx = content_cx
    seal_cy = 31.5 * mm
    _draw_award_seal(c, cx=seal_cx, cy=seal_cy, radius=14.5 * mm)

    # Left Area: Signature
    sig_cx = content_x + 38.0 * mm
    sig_line_y = 28.5 * mm
    sig_line_half = 24.0 * mm

    # Executive handwritten signature above the line
    _draw_executive_signature(c, cx=sig_cx, baseline_y=sig_line_y + 1.0 * mm)

    # Signature line
    c.setStrokeColor(colors.HexColor("#CBD5E1"))
    c.setLineWidth(0.8)
    c.line(sig_cx - sig_line_half, sig_line_y, sig_cx + sig_line_half, sig_line_y)

    # Signatory details
    # Print S. Srinivasan below it (commented out):
    # c.setFillColor(TEXT_DARK)
    # c.setFont("Helvetica-Bold", 10.5)
    # c.drawCentredString(sig_cx, sig_line_y - 4.5 * mm, "S. Srinivasan")

    # Display Director and KS Foundation beneath the name
    c.setFillColor(TEXT_MUTED)
    c.setFont("Helvetica", 8.2)
    c.drawCentredString(sig_cx, sig_line_y - 8.5 * mm, "Director")

    org_name = issuer.strip() if issuer.strip() else "KS Foundation"
    c.drawCentredString(sig_cx, sig_line_y - 12.0 * mm, org_name)

    # Right Area: Verification Details
    right_cx = content_x + content_w - 40.0 * mm

    # Gold uppercase "CERTIFICATE ID"
    _draw_tracked_centred_string(
        c,
        cx=right_cx,
        cy=40.0 * mm,
        text="CERTIFICATE ID",
        font_name="Helvetica-Bold",
        font_size=8.0,
        char_space=1.0,
        fill_color=GOLD_PRIMARY,
    )

    # Dark navy complete certificate ID
    c.setFillColor(NAVY_DARK)
    id_font_size = 7.5
    id_w = c.stringWidth(certificate_id, "Helvetica-Bold", id_font_size)
    if id_w > 65.0 * mm:
        id_font_size = max(5.5, id_font_size * (65.0 * mm / id_w))
    c.setFont("Helvetica-Bold", id_font_size)
    c.drawCentredString(right_cx, 35.0 * mm, certificate_id)

    # Shield verification icon with checkmark
    _draw_shield_icon(c, cx=right_cx, cy=28.0 * mm, size=4.8 * mm)

    # Verification URL text
    c.setFillColor(TEXT_MUTED)
    c.setFont("Helvetica", 7.2)
    c.drawCentredString(right_cx, 22.0 * mm, "Verify this certificate at:")

    # Clean verification URL
    c.setFillColor(colors.HexColor("#1D4ED8"))
    display_url = verify_url
    url_font_size = 6.2
    url_w = c.stringWidth(display_url, "Helvetica", url_font_size)
    if url_w > 68.0 * mm:
        url_font_size = max(5.0, url_font_size * (68.0 * mm / url_w))
    c.setFont("Helvetica", url_font_size)
    c.drawCentredString(right_cx, 17.5 * mm, display_url)

    c.save()
