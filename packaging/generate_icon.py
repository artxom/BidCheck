"""Generate multi-resolution Windows .ico icon for BidGuard using Pillow."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw


def generate_bidguard_ico(out_path: str | Path) -> Path:
    """Render a macOS-inspired blue squircle document badge and save as multi-size .ico."""
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    size = 512
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # Outer squircle backdrop with subtle top-to-bottom depth
    draw.rounded_rectangle((28, 28, size - 28, size - 28), radius=108, fill=(0, 96, 223, 255))
    draw.rounded_rectangle((28, 28, size - 28, size - 44), radius=104, fill=(10, 132, 255, 255))

    # Crisp document sheet inside badge
    doc_left, doc_top, doc_right, doc_bottom = 136, 108, 376, 404
    draw.rounded_rectangle(
        (doc_left, doc_top, doc_right, doc_bottom),
        radius=28,
        fill=(255, 255, 255, 250),
    )

    # Subtle document text lines
    line_color = (198, 219, 255, 255)
    draw.rounded_rectangle((172, 154, 292, 174), radius=10, fill=line_color)
    draw.rounded_rectangle((172, 196, 336, 214), radius=9, fill=line_color)

    # Verification checkmark seal
    seal_center = (256, 304)
    seal_r = 62
    draw.ellipse(
        (
            seal_center[0] - seal_r,
            seal_center[1] - seal_r,
            seal_center[0] + seal_r,
            seal_center[1] + seal_r,
        ),
        fill=(22, 163, 74, 255),
    )
    draw.line(
        [(224, 304), (247, 327), (291, 281)],
        fill=(255, 255, 255, 255),
        width=18,
        joint="curve",
    )

    icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    base_256 = canvas.resize((256, 256), Image.Resampling.LANCZOS)
    base_256.save(target, format="ICO", sizes=icon_sizes)
    return target


if __name__ == "__main__":
    output = sys.argv[1] if len(sys.argv) > 1 else "build/bidguard.ico"
    saved = generate_bidguard_ico(output)
    print(f"Generated icon: {saved}")
