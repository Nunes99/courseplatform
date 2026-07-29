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
    pdf = canvas.Canvas(buffer, pagesize=landscape(A4))
    if model == "professional":
        draw_professional_certificate(pdf, data)
    else:
        draw_participation_certificate(pdf, data)
    pdf.save()
    return buffer.getvalue()


def draw_participation_certificate(pdf: canvas.Canvas, data: dict[str, Any]) -> None:
    draw_background(pdf, CREAM)
    draw_double_frame(pdf, NAVY, GOLD)
    draw_corner_marks(pdf, NAVY)

    centered_in(pdf, issuer(data), 96, PAGE_WIDTH - 96, 520, 17, "Helvetica-Bold", BLUE)
    pdf.setStrokeColor(GOLD)
    pdf.setLineWidth(1.2)
    pdf.line(PAGE_WIDTH / 2 - 34, 500, PAGE_WIDTH / 2 + 34, 500)

    centered(pdf, "CERTIFICADO", 460, 34, "Helvetica-Bold", NAVY)
    centered(pdf, "DE PARTICIPACAO", 430, 19, "Helvetica", NAVY)
    centered(pdf, "certifica que", 394, 11, "Helvetica", MUTED)
    draw_fitted_center_block(
        pdf,
        student_name(data),
        90,
        PAGE_WIDTH - 90,
        357,
        25,
        16,
        "Helvetica-Bold",
        NAVY,
        2,
    )
    centered(pdf, "participou com sucesso do curso", 294, 11, "Helvetica", MUTED)
    draw_fitted_center_block(
        pdf,
        course_title(data),
        105,
        PAGE_WIDTH - 105,
        262,
        19,
        13,
        "Helvetica-Bold",
        BLUE,
        2,
    )

    draw_summary_panel(pdf, data.get("content_summary") or "", 105, 164, PAGE_WIDTH - 210, 58)
    draw_seal(pdf, PAGE_WIDTH / 2, 108, "LMT\nSUMMER\nSCHOOL", silver=True, radius=33)
    draw_signature(
        pdf,
        82,
        72,
        data.get("director_name") or "Diretor Academico",
        "Direcao academica",
        width=190,
    )
    draw_signature(
        pdf,
        PAGE_WIDTH - 272,
        72,
        data.get("coordinator_name") or "Coordenador do Programa",
        "Coordenacao do programa",
        width=190,
    )
    draw_certificate_footer(pdf, data)
    pdf.showPage()


def draw_professional_certificate(pdf: canvas.Canvas, data: dict[str, Any]) -> None:
    profile = data.get("certificate_profile") if isinstance(data.get("certificate_profile"), dict) else {}
    assets = profile.get("assets") if isinstance(profile.get("assets"), dict) else {}
    draw_background(pdf, colors.white)
    draw_double_frame(pdf, GOLD, NAVY)
    draw_corner_marks(pdf, NAVY)
    draw_corner_marks(pdf, GOLD, inset=18)

    left_x = 50
    left_w = 252
    right_x = 330
    right_w = PAGE_WIDTH - right_x - 50
    panel_bottom = 68
    panel_top = PAGE_HEIGHT - 50

    pdf.setFillColor(CREAM)
    pdf.setStrokeColor(colors.HexColor("#E7D4A9"))
    pdf.setLineWidth(0.8)
    pdf.roundRect(left_x, panel_bottom, left_w, panel_top - panel_bottom, 10, stroke=1, fill=1)
    pdf.setStrokeColor(HAIRLINE)
    pdf.line(316, panel_bottom, 316, panel_top)

    if not draw_image_fit(pdf, assets.get("logoUrl"), left_x + 76, 442, 100, 72):
        draw_seal(pdf, left_x + left_w / 2, 475, "LMT", silver=False, radius=31)
    centered_in(pdf, issuer(data), left_x + 18, left_x + left_w - 18, 421, 12, "Helvetica-Bold", BLUE)
    draw_fitted_center_block(
        pdf,
        clean_text(profile.get("certificateTitle") or "Certificado de Qualificacao").upper(),
        left_x + 22,
        left_x + left_w - 22,
        386,
        18,
        11.5,
        "Helvetica-Bold",
        GOLD,
        3,
    )
    draw_fitted_center_block(
        pdf,
        profile.get("qualificationType") or "sobre o aumento da qualificacao profissional",
        left_x + 24,
        left_x + left_w - 24,
        327,
        9.5,
        7.5,
        "Helvetica",
        BLUE,
        2,
    )
    centered_in(pdf, "Documento de qualificacao", left_x + 20, left_x + left_w - 20, 290, 8, "Helvetica", MUTED)
    centered_in(pdf, data.get("certificate_number") or "", left_x + 18, left_x + left_w - 18, 271, 10, "Helvetica-Bold", GOLD)

    pdf.setFillColor(colors.white)
    pdf.setStrokeColor(colors.HexColor("#E7D4A9"))
    pdf.roundRect(left_x + 24, 207, left_w - 48, 42, 6, stroke=1, fill=1)
    centered_in(pdf, "Numero de registo", left_x + 34, left_x + left_w - 34, 232, 7.5, "Helvetica", MUTED)
    centered_in(pdf, data.get("verification_code") or "", left_x + 34, left_x + left_w - 34, 216, 9, "Helvetica-Bold", NAVY)
    centered_in(pdf, profile.get("issueLocation") or "Cidade de Maputo, Mocambique", left_x + 20, left_x + left_w - 20, 174, 9.5, "Helvetica-Bold", BLUE)
    centered_in(pdf, issue_date(data), left_x + 20, left_x + left_w - 20, 155, 9, "Helvetica", MUTED)
    draw_signature(
        pdf,
        left_x + 24,
        76,
        profile.get("directorName") or data.get("director_name") or "Diretor Academico",
        profile.get("directorTitle") or "Direcao academica",
        assets.get("directorSignatureUrl"),
        width=162,
    )
    draw_image_fit(pdf, assets.get("academicStampUrl"), left_x + 182, 75, 48, 48)

    centered_in(pdf, "O presente documento certifica que", right_x + 20, right_x + right_w - 20, 510, 9.5, "Helvetica", GOLD)
    draw_fitted_center_block(
        pdf,
        student_name(data).upper(),
        right_x + 28,
        right_x + right_w - 28,
        478,
        15,
        11,
        "Helvetica-Bold",
        BLUE,
        2,
    )
    draw_wrapped_center(
        pdf,
        f"concluiu com sucesso o programa de aumento de qualificacao profissional na {issuer(data)}",
        right_x + 34,
        right_x + right_w - 34,
        431,
        9,
        "Helvetica",
        BLUE,
        2,
    )
    centered_in(pdf, "CURSO / PROGRAMA", right_x + 30, right_x + right_w - 30, 389, 8, "Helvetica-Bold", GOLD)
    draw_fitted_center_block(
        pdf,
        course_title(data),
        right_x + 28,
        right_x + right_w - 28,
        363,
        14,
        10,
        "Helvetica-Bold",
        BLUE,
        2,
    )
    draw_wrapped_center(
        pdf,
        "demonstrando aproveitamento satisfatorio em atividades academicas, estudos de caso, discussoes tecnicas e avaliacao final.",
        right_x + 34,
        right_x + right_w - 34,
        310,
        8.5,
        "Helvetica",
        MUTED,
        2,
    )
    draw_program_topics(pdf, data, right_x + 20, 156, right_w - 40, 126)
    centered_in(
        pdf,
        f"Carga horaria: {data.get('workload') or '30 horas'}",
        right_x + 20,
        right_x + right_w - 20,
        133,
        10,
        "Helvetica-Bold",
        BLUE,
    )
    draw_signature(
        pdf,
        right_x + 152,
        73,
        profile.get("coordinatorName") or data.get("coordinator_name") or "Coordenador do Programa",
        profile.get("coordinatorTitle") or "Coordenacao do programa",
        assets.get("coordinatorSignatureUrl"),
        width=176,
    )
    if not draw_image_fit(pdf, assets.get("institutionalSealUrl"), right_x + right_w - 86, 72, 62, 62):
        draw_seal(pdf, right_x + right_w - 55, 103, "L", silver=False, radius=30)
    draw_qr(pdf, right_x + 38, 72, data.get("verification_url") or "")
    draw_product_credit(pdf, profile, assets)
    draw_certificate_footer(pdf, data, show_date=False)
    pdf.showPage()


def draw_background(pdf: canvas.Canvas, color: colors.Color) -> None:
    pdf.setFillColor(color)
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, stroke=0, fill=1)
    pdf.setStrokeColor(colors.HexColor("#F0F2F5"))
    pdf.setLineWidth(0.45)
    for i in range(0, 18):
        y = 80 + i * 24
        pdf.bezier(40, y, 240, y + 32, 410, y - 28, PAGE_WIDTH - 40, y + 12)


def draw_double_frame(pdf: canvas.Canvas, primary: colors.Color, secondary: colors.Color) -> None:
    pdf.setLineWidth(3)
    pdf.setStrokeColor(primary)
    pdf.rect(18, 18, PAGE_WIDTH - 36, PAGE_HEIGHT - 36)
    pdf.setLineWidth(1.5)
    pdf.setStrokeColor(secondary)
    pdf.rect(30, 30, PAGE_WIDTH - 60, PAGE_HEIGHT - 60)


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
    height: float,
) -> None:
    pdf.setFillColor(colors.Color(1, 0.98, 0.94, alpha=0.62))
    pdf.setStrokeColor(colors.HexColor("#E7D4A9"))
    pdf.setLineWidth(0.7)
    pdf.roundRect(x, y, width, height, 8, stroke=1, fill=1)
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawString(x + 16, y + height - 21, "O programa abordou")
    topics = split_topics(data.get("content_summary") or "")
    gap = 18
    content_x = x + 16
    column_width = (width - 32 - gap) / 2
    columns = [content_x, content_x + column_width + gap]
    first_y = y + height - 43
    row_height = 23
    for index, topic in enumerate(topics[:8]):
        col = index % 2
        row = index // 2
        item_y = first_y - row * row_height
        pdf.setFillColor(GOLD)
        pdf.circle(columns[col], item_y + 2.5, 2.1, stroke=0, fill=1)
        pdf.setFillColor(INK)
        size, lines = fit_text_lines(topic, "Helvetica", 7.8, 6.8, column_width - 11, 2)
        pdf.setFont("Helvetica", size)
        for line_index, line in enumerate(lines):
            pdf.drawString(columns[col] + 8, item_y - line_index * (size + 1.6), line)


def draw_product_credit(pdf: canvas.Canvas, profile: dict[str, Any], assets: dict[str, Any]) -> None:
    logo_drawn = draw_image_fit(pdf, assets.get("productLogoUrl"), PAGE_WIDTH - 101, 507, 42, 20)
    credit = clean_text(profile.get("productCredit"))
    if not credit:
        return
    x2 = PAGE_WIDTH - 59 if not logo_drawn else PAGE_WIDTH - 105
    text = ellipsize_to_width(credit, "Helvetica", 5.5, 170)
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 5.5)
    pdf.drawRightString(x2, 498, text)


def draw_metric(pdf: canvas.Canvas, x: float, y: float, label: str, value: str) -> None:
    pdf.setStrokeColor(LIGHT_GOLD)
    pdf.setFillColor(colors.white)
    pdf.roundRect(x, y, 128, 40, 7, stroke=1, fill=1)
    centered_in(pdf, label, x, x + 128, y + 23, 7.5, "Helvetica", MUTED)
    centered_in(pdf, value, x, x + 128, y + 9, 9.5, "Helvetica-Bold", NAVY)


def draw_qr(pdf: canvas.Canvas, x: float, y: float, value: str) -> None:
    if not value:
        return
    qr_code = qr.QrCodeWidget(value)
    bounds = qr_code.getBounds()
    size = 54
    drawing = Drawing(size, size, transform=[size / (bounds[2] - bounds[0]), 0, 0, size / (bounds[3] - bounds[1]), 0, 0])
    drawing.add(qr_code)
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


def final_score(data: dict[str, Any]) -> str:
    value = data.get("final_score")
    try:
        return f"{float(value):.0f}/100"
    except (TypeError, ValueError):
        return "--/100"
