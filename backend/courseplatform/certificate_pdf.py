from __future__ import annotations

import base64
import urllib.request
from datetime import datetime
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF


PAGE_WIDTH, PAGE_HEIGHT = landscape(A4)
NAVY = colors.HexColor("#06233F")
BLUE = colors.HexColor("#123E69")
GOLD = colors.HexColor("#C9993D")
LIGHT_GOLD = colors.HexColor("#F7E3B3")
CREAM = colors.HexColor("#FFF9EC")
INK = colors.HexColor("#0B2742")
MUTED = colors.HexColor("#526173")
HAIRLINE = colors.HexColor("#DDE3EA")
SAFE_LEFT = 48
SAFE_RIGHT = PAGE_WIDTH - 48
FOOTER_Y = 47


def build_course_certificate_pdf(data: dict[str, Any], model: str = "participation") -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=landscape(A4), pageCompression=1)
    pdf.setTitle(clean_text(data.get("certificate_number") or "Certificado"))
    pdf.setAuthor(issuer(data))
    if model == "professional":
        draw_professional_certificate(pdf, data)
    else:
        draw_participation_certificate(pdf, data)
    pdf.save()
    return buffer.getvalue()


def draw_participation_certificate(pdf: canvas.Canvas, data: dict[str, Any]) -> None:
    profile = data.get("certificate_profile") if isinstance(data.get("certificate_profile"), dict) else {}
    assets = profile.get("assets") if isinstance(profile.get("assets"), dict) else {}
    draw_classic_background(pdf)
    draw_double_frame(pdf, NAVY, GOLD)

    draw_classic_brand(pdf, issuer(data), assets.get("logoUrl"))
    centered(pdf, "CERTIFICADO DE CONCLUSAO", 437, 9.5, "Helvetica-Bold", GOLD)
    centered(pdf, "Certificamos que", 407, 11, "Helvetica", MUTED)
    draw_fitted_center_block(
        pdf,
        student_name(data),
        75,
        PAGE_WIDTH - 75,
        365,
        27,
        17,
        "Helvetica-Bold",
        NAVY,
        2,
    )
    centered(pdf, "concluiu com aproveitamento o curso", 316, 10.5, "Helvetica", MUTED)
    draw_fitted_center_block(
        pdf,
        course_title(data),
        90,
        PAGE_WIDTH - 90,
        282,
        19,
        12,
        "Helvetica-Bold",
        GOLD,
        2,
    )
    draw_fitted_center_block(
        pdf,
        summary_text(data.get("content_summary") or ""),
        110,
        PAGE_WIDTH - 110,
        239,
        9.5,
        7.5,
        "Helvetica",
        MUTED,
        2,
        leading=12,
    )

    draw_classic_metrics(pdf, data)
    draw_verification_block(pdf, data, 56, 38, qr_size=58)
    draw_classic_product_credit(pdf, profile, assets)
    pdf.showPage()


def draw_professional_certificate(pdf: canvas.Canvas, data: dict[str, Any]) -> None:
    profile = data.get("certificate_profile") if isinstance(data.get("certificate_profile"), dict) else {}
    assets = profile.get("assets") if isinstance(profile.get("assets"), dict) else {}
    draw_background(pdf, colors.HexColor("#FFFDF8"), decorated=False)
    draw_double_frame(pdf, GOLD, NAVY)
    draw_corner_marks(pdf, NAVY)
    draw_corner_marks(pdf, GOLD, inset=18)

    left_x = 44
    split_x = 322
    left_w = split_x - left_x
    right_x = split_x + 18
    right_w = PAGE_WIDTH - right_x - 44
    pdf.setStrokeColor(HAIRLINE)
    pdf.setLineWidth(0.7)
    pdf.line(split_x, 52, split_x, PAGE_HEIGHT - 52)

    if not draw_image_fit(pdf, assets.get("logoUrl"), left_x + 69, 456, 140, 74):
        draw_seal(pdf, left_x + left_w / 2, 493, "LMT", silver=False, radius=31)
    centered_in(pdf, issuer(data), left_x + 20, split_x - 20, 443, 11.5, "Helvetica-Bold", GOLD)
    draw_fitted_center_block(
        pdf,
        clean_text(profile.get("certificateTitle") or "Certificado de Qualificacao").upper(),
        left_x + 22,
        split_x - 22,
        397,
        17,
        11.5,
        "Helvetica-Bold",
        GOLD,
        3,
    )
    draw_fitted_center_block(
        pdf,
        profile.get("qualificationType") or "sobre o aumento da qualificacao profissional",
        left_x + 24,
        split_x - 24,
        334,
        9.5,
        7.5,
        "Helvetica",
        BLUE,
        2,
    )
    centered_in(pdf, data.get("certificate_number") or "", left_x + 22, split_x - 22, 290, 10, "Helvetica-Bold", GOLD)
    centered_in(pdf, "Documento de qualificacao", left_x + 20, split_x - 20, 254, 8.5, "Helvetica", BLUE)
    centered_in(pdf, "Numero de registo", left_x + 24, split_x - 24, 216, 8, "Helvetica", BLUE)
    centered_in(pdf, data.get("verification_code") or "", left_x + 24, split_x - 24, 190, 10, "Helvetica-Bold", GOLD)
    centered_in(pdf, profile.get("issueLocation") or "Cidade de Maputo, Mocambique", left_x + 20, split_x - 20, 151, 10, "Helvetica-Bold", BLUE)
    centered_in(pdf, issue_date(data), left_x + 20, split_x - 20, 130, 10, "Helvetica", BLUE)
    draw_signature(
        pdf,
        left_x + 47,
        58,
        profile.get("directorName") or data.get("director_name") or "Diretor Academico",
        profile.get("directorTitle") or "Direcao academica",
        assets.get("directorSignatureUrl"),
        width=174,
    )
    draw_image_fit(pdf, assets.get("academicStampUrl"), left_x + 178, 60, 64, 64)

    centered_in(pdf, "O presente documento certifica que", right_x + 20, right_x + right_w - 20, 510, 9.5, "Helvetica", GOLD)
    draw_fitted_center_block(
        pdf,
        student_name(data).upper(),
        right_x + 28,
        right_x + right_w - 28,
        476,
        16,
        10.5,
        "Helvetica-Bold",
        BLUE,
        2,
    )
    draw_wrapped_center(
        pdf,
        f"concluiu com sucesso o programa de aumento de qualificacao profissional na {issuer(data)}",
        right_x + 34,
        right_x + right_w - 34,
        432,
        9,
        "Helvetica",
        BLUE,
        2,
    )
    centered_in(pdf, f"Emitido em {issue_date(data)}", right_x + 30, right_x + right_w - 30, 397, 9, "Helvetica", GOLD)
    centered_in(pdf, "CURSO / PROGRAMA", right_x + 30, right_x + right_w - 30, 366, 8, "Helvetica-Bold", BLUE)
    draw_fitted_center_block(
        pdf,
        course_title(data),
        right_x + 28,
        right_x + right_w - 28,
        340,
        15,
        9.5,
        "Helvetica-Bold",
        BLUE,
        2,
    )
    draw_wrapped_center(
        pdf,
        "demonstrando aproveitamento satisfatorio em atividades academicas, estudos de caso, discussoes tecnicas e avaliacao final.",
        right_x + 34,
        right_x + right_w - 34,
        298,
        8.5,
        "Helvetica",
        BLUE,
        2,
    )
    draw_program_topics(pdf, data, right_x + 30, 263, right_w - 60)
    centered_in(
        pdf,
        f"Carga horaria: {data.get('workload') or '30 horas'}",
        right_x + 20,
        right_x + right_w - 20,
        137,
        10.5,
        "Helvetica-Bold",
        BLUE,
    )
    draw_signature(
        pdf,
        right_x + 180,
        58,
        profile.get("coordinatorName") or data.get("coordinator_name") or "Coordenador do Programa",
        profile.get("coordinatorTitle") or "Coordenacao do programa",
        assets.get("coordinatorSignatureUrl"),
        width=168,
    )
    if not draw_image_fit(pdf, assets.get("institutionalSealUrl"), right_x + right_w - 93, 58, 66, 66):
        draw_seal(pdf, right_x + right_w - 60, 91, "L", silver=False, radius=31)
    draw_verification_block(pdf, data, right_x + 30, 35, qr_size=46, text_width=110)
    draw_product_credit(pdf, profile, assets)
    pdf.showPage()


def draw_background(pdf: canvas.Canvas, color: colors.Color, decorated: bool = True) -> None:
    pdf.setFillColor(color)
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, stroke=0, fill=1)
    if not decorated:
        return
    pdf.setStrokeColor(colors.HexColor("#F0F2F5"))
    pdf.setLineWidth(0.45)
    for i in range(0, 18):
        y = 80 + i * 24
        pdf.bezier(40, y, 240, y + 32, 410, y - 28, PAGE_WIDTH - 40, y + 12)


def draw_classic_background(pdf: canvas.Canvas) -> None:
    draw_background(pdf, colors.HexColor("#FFFDF8"), decorated=False)
    pdf.saveState()
    try:
        pdf.setFillAlpha(0.5)
    except AttributeError:
        pass
    pdf.setFillColor(colors.HexColor("#FFF4DB"))
    top_left = pdf.beginPath()
    top_left.moveTo(22, PAGE_HEIGHT - 22)
    top_left.lineTo(305, PAGE_HEIGHT - 22)
    top_left.lineTo(22, PAGE_HEIGHT - 318)
    top_left.close()
    pdf.drawPath(top_left, stroke=0, fill=1)
    pdf.setFillColor(colors.HexColor("#F2F7F3"))
    bottom_right = pdf.beginPath()
    bottom_right.moveTo(PAGE_WIDTH - 22, 22)
    bottom_right.lineTo(PAGE_WIDTH - 22, 305)
    bottom_right.lineTo(PAGE_WIDTH - 300, 22)
    bottom_right.close()
    pdf.drawPath(bottom_right, stroke=0, fill=1)
    pdf.restoreState()


def draw_double_frame(pdf: canvas.Canvas, primary: colors.Color, secondary: colors.Color) -> None:
    pdf.setLineWidth(7)
    pdf.setStrokeColor(primary)
    pdf.rect(10, 10, PAGE_WIDTH - 20, PAGE_HEIGHT - 20)
    pdf.setLineWidth(2)
    pdf.setStrokeColor(secondary)
    pdf.rect(20, 20, PAGE_WIDTH - 40, PAGE_HEIGHT - 40)


def draw_corner_marks(pdf: canvas.Canvas, color: colors.Color, inset: int = 0) -> None:
    pdf.setStrokeColor(color)
    pdf.setLineWidth(1.3)
    size = 42
    margin = 38 + inset
    for x, y, sx, sy in [
        (margin, PAGE_HEIGHT - margin, 1, -1),
        (PAGE_WIDTH - margin, PAGE_HEIGHT - margin, -1, -1),
        (margin, margin, 1, 1),
        (PAGE_WIDTH - margin, margin, -1, 1),
    ]:
        pdf.line(x, y, x + sx * size, y)
        pdf.line(x, y, x, y + sy * size)
        pdf.line(x + sx * 8, y + sy * 8, x + sx * (size - 8), y + sy * 8)
        pdf.line(x + sx * 8, y + sy * 8, x + sx * 8, y + sy * (size - 8))


def draw_seal(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    label: str,
    silver: bool = False,
    radius: float = 38,
) -> None:
    fill = colors.HexColor("#D7DADF") if silver else colors.HexColor("#E1B14A")
    stroke = colors.HexColor("#A9ADB5") if silver else GOLD
    pdf.setFillColor(fill)
    pdf.setStrokeColor(stroke)
    pdf.setLineWidth(2)
    pdf.circle(x, y, radius, stroke=1, fill=1)
    pdf.setFillColor(colors.white)
    pdf.circle(x, y, radius * 0.74, stroke=0, fill=1)
    pdf.setFillColor(NAVY)
    lines = str(label).split("\n")
    size = max(6, min(7.5, radius * 0.23))
    line_height = size + 4
    start_y = y + (len(lines) - 1) * line_height / 2 - size / 3
    for index, line in enumerate(lines):
        centered_in(
            pdf,
            line,
            x - radius * 0.68,
            x + radius * 0.68,
            start_y - index * line_height,
            size,
            "Helvetica-Bold",
            NAVY,
        )


def draw_signature(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    name: str,
    title: str,
    image_url: str = "",
    width: float = 180,
) -> None:
    draw_image_fit(pdf, image_url, x + (width - 92) / 2, y + 22, 92, 38)
    pdf.setStrokeColor(MUTED)
    pdf.setLineWidth(0.7)
    pdf.line(x, y + 20, x + width, y + 20)
    centered_in(pdf, name, x, x + width, y + 6, 8.5, "Helvetica-Bold", INK)
    centered_in(pdf, title, x, x + width, y - 7, 7.2, "Helvetica", MUTED)


def image_reader(value: str) -> ImageReader | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        if text.startswith("data:image/"):
            encoded = text.split(";base64,", 1)[1]
            return ImageReader(BytesIO(base64.b64decode(encoded)))
        if text.startswith(("http://", "https://")):
            with urllib.request.urlopen(text, timeout=8) as response:
                return ImageReader(BytesIO(response.read()))
    except Exception:
        return None
    return None


def draw_image_fit(pdf: canvas.Canvas, value: str, x: float, y: float, width: float, height: float) -> bool:
    reader = image_reader(value)
    if not reader:
        return False
    try:
        image_width, image_height = reader.getSize()
        scale = min(width / image_width, height / image_height)
        draw_width = image_width * scale
        draw_height = image_height * scale
        pdf.drawImage(reader, x + (width - draw_width) / 2, y + (height - draw_height) / 2, draw_width, draw_height, mask="auto")
        return True
    except Exception:
        return False


def draw_classic_brand(pdf: canvas.Canvas, name: str, logo_url: str = "") -> None:
    if draw_image_fit(pdf, logo_url, 54, 493, 188, 50):
        return
    pdf.setFillColor(LIGHT_GOLD)
    pdf.roundRect(56, 497, 38, 38, 9, stroke=0, fill=1)
    centered_in(pdf, "LMT", 56, 94, 510, 9, "Helvetica-Bold", NAVY)
    brand_size = fit_single_line_size(name, "Helvetica-Bold", 12, 8, 190)
    brand = ellipsize_to_width(name, "Helvetica-Bold", brand_size, 190)
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", brand_size)
    pdf.drawString(104, 520, brand)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 6.5)
    pdf.drawString(104, 507, "FORMACAO PROFISSIONAL")


def draw_classic_metrics(pdf: canvas.Canvas, data: dict[str, Any]) -> None:
    left = 56
    bottom = 116
    height = 62
    available = PAGE_WIDTH - left * 2
    cell_width = available / 3
    pdf.setStrokeColor(colors.HexColor("#C8D4DB"))
    pdf.setLineWidth(0.8)
    pdf.line(left, bottom + height, left + available, bottom + height)
    pdf.line(left, bottom, left + available, bottom)
    details = [
        ("RESULTADO FINAL", score_percent(data)),
        ("DATA DE EMISSAO", issue_date_long(data)),
        ("CARGA DE REFERENCIA", clean_text(data.get("workload") or "10 horas")),
    ]
    for index, (label, value) in enumerate(details):
        x = left + cell_width * index
        if index:
            pdf.line(x, bottom, x, bottom + height)
        centered_in(pdf, label, x + 12, x + cell_width - 12, bottom + 39, 7, "Helvetica-Bold", MUTED)
        centered_in(pdf, value, x + 12, x + cell_width - 12, bottom + 20, 9.5, "Helvetica-Bold", NAVY)


def draw_verification_block(
    pdf: canvas.Canvas,
    data: dict[str, Any],
    x: float,
    y: float,
    qr_size: float = 54,
    text_width: float = 150,
) -> None:
    draw_qr(pdf, x, y, data.get("verification_url") or "", size=qr_size)
    text_x = x + qr_size + 14
    code = clean_text(data.get("verification_code") or data.get("certificate_number") or "")
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica-Bold", 6.2)
    pdf.drawString(text_x, y + qr_size * 0.55, "CODIGO DE VERIFICACAO")
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 7.5)
    pdf.drawString(
        text_x,
        y + qr_size * 0.30,
        ellipsize_to_width(code, "Helvetica-Bold", 7.5, text_width),
    )


def draw_classic_product_credit(
    pdf: canvas.Canvas,
    profile: dict[str, Any],
    assets: dict[str, Any],
) -> None:
    right = PAGE_WIDTH - 56
    if not draw_image_fit(pdf, assets.get("productLogoUrl"), right - 92, 73, 92, 24):
        centered_in(pdf, issuer({"issuer_name": profile.get("issuerName")}), right - 180, right, 79, 8, "Helvetica-Bold", NAVY)
    credit = clean_text(profile.get("productCredit"))
    if credit:
        size, lines = fit_text_lines(credit, "Helvetica", 6.2, 5.3, 210, 2)
        pdf.setFillColor(MUTED)
        pdf.setFont("Helvetica", size)
        for index, line in enumerate(lines):
            pdf.drawRightString(right, 61 - index * (size + 2), line)


def draw_summary_panel(
    pdf: canvas.Canvas,
    value: str,
    x: float,
    y: float,
    width: float,
    height: float,
) -> None:
    if not clean_text(value):
        return
    summary = " - ".join(
        line.strip(" -\t")
        for line in clean_text(value).splitlines()
        if line.strip(" -\t")
    )
    pdf.setFillColor(colors.Color(1, 1, 1, alpha=0.72))
    pdf.setStrokeColor(colors.HexColor("#E7D4A9"))
    pdf.setLineWidth(0.7)
    pdf.roundRect(x, y, width, height, 8, stroke=1, fill=1)
    draw_fitted_center_block(
        pdf,
        summary,
        x + 22,
        x + width - 22,
        y + height - 22,
        9.5,
        8,
        "Helvetica",
        MUTED,
        3,
        leading=12,
    )


def draw_program_topics(
    pdf: canvas.Canvas,
    data: dict[str, Any],
    x: float,
    y: float,
    width: float,
) -> None:
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica", 9.5)
    pdf.drawCentredString(x + width / 2, y, "O programa abordou:")
    topics = split_topics(data.get("content_summary") or "")
    gap = 22
    column_width = (width - gap) / 2
    columns = [x, x + column_width + gap]
    first_y = y - 26
    row_height = 21
    for index, topic in enumerate(topics[:8]):
        col = index % 2
        row = index // 2
        item_y = first_y - row * row_height
        pdf.setFillColor(NAVY)
        pdf.circle(columns[col], item_y + 2.4, 1.55, stroke=0, fill=1)
        size, lines = fit_text_lines(topic, "Helvetica", 7.3, 6.4, column_width - 11, 2)
        pdf.setFont("Helvetica", size)
        for line_index, line in enumerate(lines):
            pdf.drawString(columns[col] + 8, item_y - line_index * (size + 1.6), line)


def draw_product_credit(pdf: canvas.Canvas, _profile: dict[str, Any], assets: dict[str, Any]) -> None:
    draw_image_fit(pdf, assets.get("productLogoUrl"), 134, 414, 70, 16)


def draw_metric(pdf: canvas.Canvas, x: float, y: float, label: str, value: str) -> None:
    pdf.setStrokeColor(LIGHT_GOLD)
    pdf.setFillColor(colors.white)
    pdf.roundRect(x, y, 128, 40, 7, stroke=1, fill=1)
    centered_in(pdf, label, x, x + 128, y + 23, 7.5, "Helvetica", MUTED)
    centered_in(pdf, value, x, x + 128, y + 9, 9.5, "Helvetica-Bold", NAVY)


def draw_qr(pdf: canvas.Canvas, x: float, y: float, value: str, size: float = 54) -> None:
    if not value:
        return
    qr_code = qr.QrCodeWidget(value)
    bounds = qr_code.getBounds()
    quiet = size * 0.08
    drawing = Drawing(
        size,
        size,
        transform=[
            (size - quiet * 2) / (bounds[2] - bounds[0]),
            0,
            0,
            (size - quiet * 2) / (bounds[3] - bounds[1]),
            quiet,
            quiet,
        ],
    )
    drawing.add(qr_code)
    pdf.setFillColor(colors.white)
    pdf.setStrokeColor(colors.HexColor("#C8D4DB"))
    pdf.setLineWidth(0.7)
    pdf.rect(x, y, size, size, stroke=1, fill=1)
    renderPDF.draw(drawing, pdf, x, y)


def draw_certificate_footer(pdf: canvas.Canvas, data: dict[str, Any], show_date: bool = True) -> None:
    pdf.setStrokeColor(colors.HexColor("#D9DEE5"))
    pdf.setLineWidth(0.55)
    pdf.line(SAFE_LEFT, FOOTER_Y + 13, SAFE_RIGHT, FOOTER_Y + 13)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 7)
    certificate_text = ellipsize_to_width(
        f"N. do certificado: {data.get('certificate_number') or ''}",
        "Helvetica",
        7,
        240,
    )
    code_text = ellipsize_to_width(
        f"Codigo: {data.get('verification_code') or ''}",
        "Helvetica",
        7,
        220,
    )
    pdf.drawString(SAFE_LEFT, FOOTER_Y, certificate_text)
    if show_date:
        centered(pdf, f"Emitido em {issue_date(data)}", FOOTER_Y, 7, "Helvetica", MUTED)
    pdf.drawRightString(SAFE_RIGHT, FOOTER_Y, code_text)


def centered(pdf: canvas.Canvas, text: str, y: float, size: float, font: str, color: colors.Color) -> None:
    centered_in(pdf, text, 0, PAGE_WIDTH, y, size, font, color)


def centered_in(pdf: canvas.Canvas, text: str, x1: float, x2: float, y: float, size: float, font: str, color: colors.Color) -> None:
    text = clean_inline_text(text)
    size = fit_single_line_size(text, font, size, max(5.5, size * 0.7), x2 - x1)
    text = ellipsize_to_width(text, font, size, x2 - x1)
    pdf.setFillColor(color)
    pdf.setFont(font, size)
    width = stringWidth(text, font, size)
    pdf.drawString(x1 + ((x2 - x1 - width) / 2), y, text)


def draw_wrapped_center(
    pdf: canvas.Canvas,
    text: str,
    x1: float,
    x2: float,
    y: float,
    size: float,
    font: str,
    color: colors.Color,
    max_lines: int,
) -> float:
    fitted_size, lines = fit_text_lines(text, font, size, max(6.5, size * 0.78), x2 - x1, max_lines)
    leading = fitted_size + 3
    for index, line in enumerate(lines):
        centered_in(pdf, line, x1, x2, y - index * leading, fitted_size, font, color)
    return y - max(0, len(lines) - 1) * leading


def draw_fitted_center_block(
    pdf: canvas.Canvas,
    text: str,
    x1: float,
    x2: float,
    y: float,
    max_size: float,
    min_size: float,
    font: str,
    color: colors.Color,
    max_lines: int,
    leading: float | None = None,
) -> float:
    size, lines = fit_text_lines(text, font, max_size, min_size, x2 - x1, max_lines)
    line_height = leading or size * 1.24
    for index, line in enumerate(lines):
        centered_in(pdf, line, x1, x2, y - index * line_height, size, font, color)
    return y - max(0, len(lines) - 1) * line_height


def fit_text_lines(
    value: Any,
    font: str,
    max_size: float,
    min_size: float,
    max_width: float,
    max_lines: int,
) -> tuple[float, list[str]]:
    text = clean_inline_text(value)
    if not text:
        return max_size, [""]
    size = max_size
    while size >= min_size:
        lines = wrap_text_to_width(text, font, size, max_width)
        if len(lines) <= max_lines:
            return size, lines
        size -= 0.5
    size = min_size
    lines = wrap_text_to_width(text, font, size, max_width)
    if len(lines) > max_lines:
        visible = lines[:max_lines]
        remaining = " ".join(lines[max_lines - 1 :])
        visible[-1] = ellipsize_to_width(remaining, font, size, max_width)
        return size, visible
    return size, lines


def fit_single_line_size(
    value: Any,
    font: str,
    max_size: float,
    min_size: float,
    max_width: float,
) -> float:
    text = clean_inline_text(value)
    size = max_size
    while size > min_size and stringWidth(text, font, size) > max_width:
        size -= 0.5
    return max(size, min_size)


def wrap_text_to_width(value: Any, font: str, size: float, max_width: float) -> list[str]:
    text = clean_inline_text(value)
    if not text:
        return []
    words = text.split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if stringWidth(candidate, font, size) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
            current = ""
        if stringWidth(word, font, size) <= max_width:
            current = word
            continue
        fragments = split_token_to_width(word, font, size, max_width)
        lines.extend(fragments[:-1])
        current = fragments[-1]
    if current:
        lines.append(current)
    return lines


def split_token_to_width(token: str, font: str, size: float, max_width: float) -> list[str]:
    fragments: list[str] = []
    current = ""
    for character in token:
        candidate = current + character
        if current and stringWidth(candidate, font, size) > max_width:
            fragments.append(current)
            current = character
        else:
            current = candidate
    if current:
        fragments.append(current)
    return fragments or [""]


def ellipsize_to_width(value: Any, font: str, size: float, max_width: float) -> str:
    text = clean_inline_text(value)
    if stringWidth(text, font, size) <= max_width:
        return text
    suffix = "..."
    while text and stringWidth(text.rstrip() + suffix, font, size) > max_width:
        text = text[:-1]
    return text.rstrip() + suffix


def split_topics(value: str) -> list[str]:
    topics = []
    for line in clean_text(value).splitlines():
        text = line.strip(" -\t")
        if text:
            topics.append(text)
    return topics or ["Conteudos essenciais do curso", "Atividades praticas", "Avaliacoes e acompanhamento"]


def summary_text(value: Any) -> str:
    return " - ".join(
        line.strip(" -\t")
        for line in clean_text(value).splitlines()
        if line.strip(" -\t")
    )


def clean_text(value: Any) -> str:
    return str(value or "").replace("\r", "").strip()


def clean_inline_text(value: Any) -> str:
    return " ".join(clean_text(value).split())


def issuer(data: dict[str, Any]) -> str:
    return clean_text(data.get("issuer_name") or "LMTWEBNAIRS Summer School")


def student_name(data: dict[str, Any]) -> str:
    return clean_text(data.get("student_name") or "Nome do participante")


def course_title(data: dict[str, Any]) -> str:
    return clean_text(data.get("course_title") or "Curso")


def issue_date(data: dict[str, Any]) -> str:
    value = data.get("issue_date")
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    text = clean_text(value)
    if not text:
        return datetime.utcnow().strftime("%d/%m/%Y")
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except ValueError:
        return text[:10]


def issue_date_long(data: dict[str, Any]) -> str:
    short_date = issue_date(data)
    try:
        parsed = datetime.strptime(short_date, "%d/%m/%Y")
    except ValueError:
        return short_date
    months = [
        "janeiro",
        "fevereiro",
        "marco",
        "abril",
        "maio",
        "junho",
        "julho",
        "agosto",
        "setembro",
        "outubro",
        "novembro",
        "dezembro",
    ]
    return f"{parsed.day} de {months[parsed.month - 1]} de {parsed.year}"


def score_percent(data: dict[str, Any]) -> str:
    value = data.get("final_score")
    try:
        return f"{float(value):.0f}%"
    except (TypeError, ValueError):
        return "--"


def final_score(data: dict[str, Any]) -> str:
    value = data.get("final_score")
    try:
        return f"{float(value):.0f}/100"
    except (TypeError, ValueError):
        return "--/100"
