from __future__ import annotations

from datetime import datetime
from io import BytesIO
from textwrap import wrap
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
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

    centered(pdf, issuer(data), PAGE_HEIGHT - 58, 20, "Helvetica-Bold", BLUE)
    centered(pdf, "CERTIFICADO", PAGE_HEIGHT - 112, 34, "Helvetica-Bold", NAVY)
    centered(pdf, "DE PARTICIPACAO", PAGE_HEIGHT - 142, 23, "Helvetica", NAVY)
    centered(pdf, "certifica que", PAGE_HEIGHT - 188, 12, "Helvetica", MUTED)
    centered(pdf, student_name(data), PAGE_HEIGHT - 224, 25, "Helvetica-Bold", NAVY)
    centered(pdf, "participou com sucesso do curso", PAGE_HEIGHT - 258, 12, "Helvetica", MUTED)
    centered(pdf, course_title(data), PAGE_HEIGHT - 292, 18, "Helvetica-Bold", BLUE)

    summary_lines = wrap_text(data.get("content_summary") or "", 82, 3)
    y = PAGE_HEIGHT - 322
    for line in summary_lines:
        centered(pdf, line, y, 9.5, "Helvetica", MUTED)
        y -= 14

    draw_seal(pdf, PAGE_WIDTH / 2, 128, "LMT\nSUMMER\nSCHOOL", silver=True)
    draw_signature(pdf, 92, 82, data.get("director_name") or "Diretor Academico", "Direcao academica")
    draw_signature(pdf, PAGE_WIDTH - 262, 82, data.get("coordinator_name") or "Coordenador do Programa", "Coordenacao do programa")
    draw_certificate_footer(pdf, data)
    pdf.showPage()


def draw_professional_certificate(pdf: canvas.Canvas, data: dict[str, Any]) -> None:
    draw_background(pdf, colors.white)
    draw_double_frame(pdf, GOLD, NAVY)
    draw_corner_marks(pdf, NAVY)
    draw_corner_marks(pdf, GOLD, inset=18)

    left_x = 62
    left_w = 270
    right_x = 382
    right_w = PAGE_WIDTH - right_x - 62
    top_y = PAGE_HEIGHT - 68

    draw_seal(pdf, left_x + left_w / 2, top_y - 4, "LMT", silver=False)
    centered_in(pdf, issuer(data), left_x, left_x + left_w, top_y - 72, 13, "Helvetica-Bold", LIGHT_GOLD)
    centered_in(pdf, "CERTIFICADO DE", left_x, left_x + left_w, top_y - 112, 19, "Helvetica-Bold", GOLD)
    centered_in(pdf, "QUALIFICACAO", left_x, left_x + left_w, top_y - 136, 19, "Helvetica-Bold", GOLD)
    centered_in(pdf, "sobre o aumento da qualificacao profissional", left_x, left_x + left_w, top_y - 162, 10, "Helvetica", BLUE)
    centered_in(pdf, data.get("certificate_number") or "", left_x, left_x + left_w, top_y - 184, 10, "Helvetica-Bold", GOLD)
    centered_in(pdf, "Documento de qualificacao", left_x, left_x + left_w, top_y - 214, 9, "Helvetica", BLUE)
    centered_in(pdf, "Numero de registo", left_x, left_x + left_w, top_y - 258, 9, "Helvetica", BLUE)
    centered_in(pdf, data.get("verification_code") or "", left_x, left_x + left_w, top_y - 286, 10, "Helvetica-Bold", GOLD)
    centered_in(pdf, "Cidade de Maputo, Mocambique", left_x, left_x + left_w, 142, 11, "Helvetica-Bold", BLUE)
    centered_in(pdf, issue_date(data), left_x, left_x + left_w, 118, 11, "Helvetica", BLUE)
    draw_signature(pdf, left_x + 44, 62, data.get("director_name") or "Diretor Academico", "LMTWEBNAIRS")

    centered_in(pdf, "O presente documento certifica que", right_x, right_x + right_w, top_y - 18, 10, "Helvetica", GOLD)
    centered_in(pdf, student_name(data).upper(), right_x, right_x + right_w, top_y - 52, 14, "Helvetica-Bold", BLUE)
    draw_wrapped_center(pdf, "concluiu com sucesso o programa de aumento de qualificacao profissional na LMTWEBNAIRS Summer School", right_x + 36, right_x + right_w - 36, top_y - 82, 9, "Helvetica", BLUE, 2)
    centered_in(pdf, "curso/programa", right_x, right_x + right_w, top_y - 132, 9, "Helvetica", GOLD)
    centered_in(pdf, course_title(data), right_x, right_x + right_w, top_y - 160, 13, "Helvetica-Bold", BLUE)
    draw_wrapped_center(pdf, "demonstrando aproveitamento satisfatorio em atividades academicas, estudos de caso, discussoes tecnicas e avaliacao final.", right_x + 34, right_x + right_w - 34, top_y - 190, 9, "Helvetica", BLUE, 3)
    draw_program_topics(pdf, data, right_x + 52, top_y - 260)
    centered_in(pdf, f"Carga horaria: {data.get('workload') or '30 horas'}", right_x, right_x + right_w, 146, 12, "Helvetica-Bold", BLUE)
    draw_signature(pdf, right_x + 120, 72, data.get("coordinator_name") or "Coordenador do Programa", "LMTWEBNAIRS")
    draw_seal(pdf, right_x + right_w - 70, 86, "L", silver=False)
    draw_qr(pdf, right_x + 42, 42, data.get("verification_url") or "")
    draw_certificate_footer(pdf, data, show_date=False)
    pdf.showPage()


def draw_background(pdf: canvas.Canvas, color: colors.Color) -> None:
    pdf.setFillColor(color)
    pdf.rect(0, 0, PAGE_WIDTH, PAGE_HEIGHT, stroke=0, fill=1)
    pdf.setStrokeColor(colors.HexColor("#EDF0F4"))
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


def draw_seal(pdf: canvas.Canvas, x: float, y: float, label: str, silver: bool = False) -> None:
    fill = colors.HexColor("#D7DADF") if silver else colors.HexColor("#E1B14A")
    stroke = colors.HexColor("#A9ADB5") if silver else GOLD
    pdf.setFillColor(fill)
    pdf.setStrokeColor(stroke)
    pdf.setLineWidth(2)
    pdf.circle(x, y, 38, stroke=1, fill=1)
    pdf.setFillColor(colors.white)
    pdf.circle(x, y, 28, stroke=0, fill=1)
    pdf.setFillColor(NAVY)
    lines = str(label).split("\n")
    start_y = y + (len(lines) - 1) * 6
    for index, line in enumerate(lines):
        centered_in(pdf, line, x - 25, x + 25, start_y - index * 12, 7.5, "Helvetica-Bold", NAVY)


def draw_signature(pdf: canvas.Canvas, x: float, y: float, name: str, title: str) -> None:
    pdf.setStrokeColor(MUTED)
    pdf.setLineWidth(0.7)
    pdf.line(x, y + 20, x + 180, y + 20)
    centered_in(pdf, name, x, x + 180, y + 6, 9, "Helvetica-Bold", INK)
    centered_in(pdf, title, x, x + 180, y - 7, 7.5, "Helvetica", MUTED)


def draw_program_topics(pdf: canvas.Canvas, data: dict[str, Any], x: float, y: float) -> None:
    pdf.setFillColor(NAVY)
    pdf.setFont("Helvetica-Bold", 10)
    pdf.drawString(x, y, "O programa abordou:")
    topics = split_topics(data.get("content_summary") or "")
    columns = [x, x + 245]
    for index, topic in enumerate(topics[:8]):
        col = index % 2
        row = index // 2
        pdf.setFillColor(GOLD)
        pdf.circle(columns[col], y - 24 - row * 18, 2.3, stroke=0, fill=1)
        pdf.setFillColor(INK)
        pdf.setFont("Helvetica", 8.2)
        pdf.drawString(columns[col] + 8, y - 27 - row * 18, trim(topic, 44))


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
    pdf.setFillColor(MUTED)
    pdf.setFont("Helvetica", 7.5)
    pdf.drawString(48, 34, f"N. do certificado: {data.get('certificate_number') or ''}")
    if show_date:
        centered(pdf, f"Emitido em {issue_date(data)}", 34, 7.5, "Helvetica", MUTED)
    pdf.drawRightString(PAGE_WIDTH - 48, 34, f"Codigo: {data.get('verification_code') or ''}")


def centered(pdf: canvas.Canvas, text: str, y: float, size: float, font: str, color: colors.Color) -> None:
    centered_in(pdf, text, 0, PAGE_WIDTH, y, size, font, color)


def centered_in(pdf: canvas.Canvas, text: str, x1: float, x2: float, y: float, size: float, font: str, color: colors.Color) -> None:
    text = trim(text, max(14, int((x2 - x1) / max(size * 0.52, 1))))
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
) -> None:
    length = max(18, int((x2 - x1) / max(size * 0.72, 1)))
    lines = wrap_text(text, length, max_lines)
    for index, line in enumerate(lines):
        centered_in(pdf, line, x1, x2, y - index * (size + 4), size, font, color)


def wrap_text(value: str, length: int, max_lines: int) -> list[str]:
    return wrap(clean_text(value), width=length)[:max_lines]


def split_topics(value: str) -> list[str]:
    topics = []
    for line in clean_text(value).splitlines():
        text = line.strip(" -\t")
        if text:
            topics.append(text)
    return topics or ["Conteudos essenciais do curso", "Atividades praticas", "Avaliacoes e acompanhamento"]


def trim(value: Any, length: int) -> str:
    text = clean_text(value)
    return text if len(text) <= length else f"{text[: max(0, length - 3)].rstrip()}..."


def clean_text(value: Any) -> str:
    return str(value or "").replace("\r", "").strip()


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
