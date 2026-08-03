"""Generate the raster PWA icons from the platform's compact brand mark.

Pillow is only needed when regenerating assets; the application does not import
it at runtime.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIRECTORY = ROOT / "public" / "assets"


def point(value: float, scale: float) -> int:
    return round(value * scale)


def icon(size: int) -> Image.Image:
    supersampling = 4
    canvas_size = size * supersampling
    scale = canvas_size / 512
    image = Image.new("RGB", (canvas_size, canvas_size), "#00365B")
    draw = ImageDraw.Draw(image)
    draw.polygon(
        [(point(x, scale), point(y, scale)) for x, y in ((104, 174), (256, 92), (408, 174), (256, 256))],
        fill="#EAC78B",
    )
    draw.polygon(
        [(point(x, scale), point(y, scale)) for x, y in ((148, 222), (256, 280), (364, 222), (364, 334), (148, 334))],
        fill="#FFF8E4",
    )
    draw.ellipse(
        (point(148, scale), point(294, scale), point(364, scale), point(406, scale)),
        fill="#FFF8E4",
    )
    tassel_width = max(1, point(24, scale))
    draw.line(
        [(point(408, scale), point(181, scale)), (point(408, scale), point(307, scale))],
        fill="#C9A55B",
        width=tassel_width,
    )
    draw.ellipse(
        (point(388, scale), point(312, scale), point(428, scale), point(352, scale)),
        fill="#C9A55B",
    )
    return image.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    ASSET_DIRECTORY.mkdir(parents=True, exist_ok=True)
    for size in (180, 192, 512):
        icon(size).save(ASSET_DIRECTORY / f"app-icon-{size}.png", optimize=True)


if __name__ == "__main__":
    main()
