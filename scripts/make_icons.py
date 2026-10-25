#!/usr/bin/env python3
"""Generate the PWA icons from scratch, so they're reproducible rather than
mystery binaries in the repo. Re-run after changing the mark or palette:

    python3 scripts/make_icons.py

The mark is three descending rungs -- the ladder this whole system is built
around -- on the dashboard's accent colour.
"""
import pathlib

from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parent.parent
ICONS = ROOT / "icons"

ACCENT = (168, 99, 31)        # --accent from the dashboard stylesheet
INK = (255, 250, 244)         # warm white, readable on the accent

# Opacity per rung: the deepest step fades, suggesting a level not yet
# reached. Kept well above 50% so all three still read at 48px, which is
# where Android actually draws this.
RUNG_ALPHA = (255, 235, 180)


def draw_mark(size: int, inset: float) -> Image.Image:
    """Square icon, `inset` being the fraction of the canvas kept clear.

    Maskable icons get a bigger inset: Android crops them to whatever shape
    the launcher uses, and only the middle ~80% is guaranteed to survive.
    """
    img = Image.new("RGBA", (size, size), ACCENT + (255,))
    d = ImageDraw.Draw(img)

    pad = size * inset
    usable = size - 2 * pad
    # Three rungs, each lower and shorter -- price stepping down the ladder.
    widths = (1.0, 0.78, 0.56)
    bar_h = usable * 0.15
    gap = (usable - 3 * bar_h) / 2

    for i, frac in enumerate(widths):
        top = pad + i * (bar_h + gap)
        width = usable * frac
        left = pad
        d.rounded_rectangle(
            [left, top, left + width, top + bar_h],
            radius=bar_h / 2,
            fill=INK + (RUNG_ALPHA[i],),
        )
    return img


def rounded_square(img: Image.Image, radius_frac: float = 0.22) -> Image.Image:
    """Round the corners for the non-maskable icons, which are shown as-is."""
    size = img.size[0]
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size - 1, size - 1], radius=size * radius_frac, fill=255
    )
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def main() -> None:
    ICONS.mkdir(exist_ok=True)
    written = []

    for size in (192, 512):
        icon = rounded_square(draw_mark(size, inset=0.22))
        path = ICONS / f"icon-{size}.png"
        icon.save(path)
        written.append(path)

    # Maskable: full-bleed background, mark pulled well inside the safe zone.
    maskable = draw_mark(512, inset=0.30)
    maskable.save(ICONS / "icon-maskable-512.png")
    written.append(ICONS / "icon-maskable-512.png")

    # iOS home-screen icon: no transparency, no rounding (iOS adds its own).
    apple = draw_mark(180, inset=0.22).convert("RGB")
    apple.save(ICONS / "apple-touch-icon.png")
    written.append(ICONS / "apple-touch-icon.png")

    for path in written:
        print(f"{path.relative_to(ROOT)}  {path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()
