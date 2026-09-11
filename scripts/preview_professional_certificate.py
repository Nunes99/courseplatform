"""Render a synthetic certificate and independently decode the printed QR code."""
import json
import sys
from pathlib import Path

import pypdfium2
import zxingcpp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.courseplatform.certificate_pdf import build_course_certificate_pdf


def main():
    data = json.loads((ROOT / "tests/fixtures/professional_certificate.json").read_text(encoding="utf-8"))
    output = ROOT / "output/pdf/certificate-professional-layout.pdf"
    output.parent.mkdir(parents=True, exist_ok=True)
    pdf = build_course_certificate_pdf(data, "professional")
    output.write_bytes(pdf)
    with pypdfium2.PdfDocument(pdf) as document:
        image = document[0].render(scale=2.5).to_pil()
        preview = ROOT / "tmp/pdfs/professional-layout.png"
        preview.parent.mkdir(parents=True, exist_ok=True)
        image.save(preview)
        codes = zxingcpp.read_barcodes(image)
        assert any(code.text == data["verification_url"] for code in codes), "PDF QR is not readable"
    print(f"PDF A4 and QR verified: {output}")


if __name__ == "__main__":
    main()
