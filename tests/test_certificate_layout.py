import copy
import base64
import json
import unittest
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader
from PIL import Image
from backend.courseplatform.certificate_pdf import (
    CertificateLayoutError, FONT_BOLD, FONT_REGULAR, build_course_certificate_pdf,
    fit_certificate_box, professional_layout, professional_text_blocks, stringWidth,
)


FIXTURE = Path(__file__).parent / "fixtures/professional_certificate.json"


class CertificateLayoutTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.layout = professional_layout()

    def test_stamp_overlay_stays_within_the_director_block(self):
        boxes = {**self.layout["texts"], **self.layout["images"]}
        qr = self.layout["qr"]
        boxes["qr"] = {**qr, "w": qr["size"], "h": qr["size"]}
        boxes["topics"] = self.layout["topics"]
        for key, box in boxes.items():
            self.assertGreaterEqual(box["x"], 22, key)
            self.assertGreaterEqual(box["y"], 22, key)
            self.assertLessEqual(box["x"] + box["w"], self.layout["width"] - 22, key)
            self.assertLessEqual(box["y"] + box["h"], self.layout["height"] - 22, key)
        items = list(boxes.items())
        intentional_overlap = {"academicStampUrl", "directorSignatureUrl"}
        # Reserved label boxes include whitespace beside the centered text.
        stamp_label_boxes = (
            {"academicStampUrl", "director"},
            {"academicStampUrl", "directorTitle"},
        )
        for index, (name, a) in enumerate(items):
            for other, b in items[index + 1:]:
                overlap = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"]) > 0
                overlap &= min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"]) > 0
                if {name, other} == intentional_overlap:
                    self.assertTrue(overlap, "Stamp must overlap the director signature")
                elif {name, other} not in stamp_label_boxes:
                    self.assertFalse(overlap, f"{name} overlaps {other}")
        image_order = list(self.layout["images"])
        self.assertGreater(image_order.index("academicStampUrl"), image_order.index("directorSignatureUrl"))

    def test_director_signature_keeps_original_left_and_baseline_anchors(self):
        signature = self.layout["images"]["directorSignatureUrl"]
        self.assertEqual(signature["x"], 124)
        self.assertEqual(signature["y"] + signature["h"], 455)
        self.assertEqual((signature["w"], signature["h"]), (168, 44))
        stamp = self.layout["images"]["academicStampUrl"]
        self.assertEqual((stamp["w"], stamp["h"]), (100, 100))
        self.assertEqual((stamp["x"], stamp["y"]), (232, 412))
        self.assertEqual(signature["x"] + signature["w"] - stamp["x"], 60)
        for key in ("director", "directorTitle"):
            text = self.layout["texts"][key]
            self.assertEqual(text["x"] + text["w"] / 2, 184)

    def test_stamp_clears_rendered_director_labels_in_reference_certificate(self):
        stamp = self.layout["images"]["academicStampUrl"]
        for key, value, box in professional_text_blocks(self.data, self.layout):
            if key not in ("director", "directorTitle"):
                continue
            size, lines = fit_certificate_box(value, box, key)
            font = FONT_BOLD if box.get("bold") else FONT_REGULAR
            for line in lines:
                right = box["x"] + (box["w"] + stringWidth(line, font, size)) / 2
                self.assertLess(right, stamp["x"], key)

    def test_long_text_is_complete_inside_its_reserved_area(self):
        self.data["student_name"] = "Ana Sofia Luís de Almeida e Vasconcelos Chissano"
        self.data["course_title"] = "Economia Industrial, Análise de Investimentos e Gestão de Projetos Energéticos"
        self.data["content_summary"] += "\nAvaliação económica de projetos\nSegurança e responsabilidade social"
        for key, value, box in professional_text_blocks(self.data, self.layout):
            size, lines = fit_certificate_box(value, box, key)
            self.assertGreaterEqual(size, box["min"], key)
            self.assertLessEqual(len(lines) * size * 1.22, box["h"] + .01, key)
            self.assertEqual(" ".join(lines), " ".join(str(value).split()), key)
            font = FONT_BOLD if box.get("bold") else FONT_REGULAR
            for line in lines:
                self.assertLessEqual(stringWidth(line, font, size), box["w"] + .01, key)

    def test_excessive_content_is_reported_not_silently_truncated(self):
        self.data["content_summary"] = "\n".join(f"Conteúdo {n}" for n in range(9))
        with self.assertRaisesRegex(CertificateLayoutError, "oito"):
            build_course_certificate_pdf(self.data, "professional")
        self.data["content_summary"] = ""
        self.data["student_name"] = "Nome muito longo " * 40
        with self.assertRaisesRegex(CertificateLayoutError, "student"):
            build_course_certificate_pdf(self.data, "professional")

    def test_pdf_is_one_landscape_a4_page_with_complete_text_and_link(self):
        reader = PdfReader(BytesIO(build_course_certificate_pdf(self.data, "professional")))
        self.assertEqual(len(reader.pages), 1)
        page = reader.pages[0]
        self.assertAlmostEqual(float(page.mediabox.width), self.layout["width"], places=2)
        self.assertAlmostEqual(float(page.mediabox.height), self.layout["height"], places=2)
        text = " ".join(page.extract_text().split())
        for value in [self.data["student_name"], self.data["course_title"], self.data["verification_code"], "96%", "36 horas"]:
            self.assertIn(value, text)
        links = [item.get_object().get("/A", {}).get("/URI") for item in page.get("/Annots", [])]
        self.assertIn(self.data["verification_url"], links)

    def test_zero_score_and_march_are_preserved(self):
        self.data.update(final_score=0, issue_date="2026-03-20T10:00:00Z")
        text = PdfReader(BytesIO(build_course_certificate_pdf(self.data, "professional"))).pages[0].extract_text()
        self.assertIn("0%", text)
        self.assertIn("março", text)

    def test_optional_images_do_not_change_layout_or_mutate_snapshot(self):
        original = copy.deepcopy(self.data)
        build_course_certificate_pdf(self.data, "professional")
        self.assertEqual(original, self.data)

    def test_all_six_optional_assets_render_with_different_aspect_ratios(self):
        for index, key in enumerate(self.layout["images"]):
            buffer = BytesIO()
            size = [(240, 80), (320, 60), (120, 180)][index % 3]
            Image.new("RGB", size, (30 + index * 25, 80, 110)).save(buffer, format="PNG")
            self.data["certificate_profile"]["assets"][key] = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")
        reader = PdfReader(BytesIO(build_course_certificate_pdf(self.data, "professional")))
        self.assertEqual(len(reader.pages[0].images), 6)
        self.assertIn(self.data["student_name"], reader.pages[0].extract_text())

    def test_public_and_packaged_layouts_match(self):
        public = Path(__file__).resolve().parents[1] / "public/assets/certificate-layout.json"
        self.assertEqual(json.loads(public.read_text(encoding="utf-8")), self.layout)


if __name__ == "__main__":
    unittest.main()
