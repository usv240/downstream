"""Generate a synthetic 1958-style drawing with adjacent ground truth."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent / "fixtures"


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1500, 1000), "#f4efe0")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=24)
    small = ImageFont.load_default(size=18)
    draw.rectangle((55, 55, 1445, 945), outline="#273b47", width=5)
    draw.line((120, 630, 560, 330, 980, 630), fill="#273b47", width=12)
    draw.line((560, 330, 560, 720), fill="#273b47", width=5)
    draw.line((960, 500, 1280, 500), fill="#416b82", width=15)
    draw.text((110, 100), "CEDAR HOLLOW DEMONSTRATION DAM", fill="#273b47", font=font)
    draw.text((110, 145), "GENERAL ARRANGEMENT  |  SHEET 2 OF 5  |  1958", fill="#273b47", font=small)
    draw.text((500, 270), "TOP OF DAM EL. 742.6", fill="#273b47", font=small)
    draw.text((895, 440), "CONC. O.F. SPILLWAY 18'-0\"", fill="#273b47", font=small)
    draw.text((610, 550), "MAX. EMBANKMENT HT. 31 FT", fill="#273b47", font=small)
    draw.text((1060, 845), "SYNTHETIC FIXTURE | NO AGENCY SEAL", fill="#6b4b3a", font=small)
    image.save(ROOT / "cedar_hollow_drawing.png")
    truth = {
        "synthetic": True,
        "facts": {
            "crest_elevation": "742.6",
            "spillway": "concrete overflow spillway, 18 ft",
            "dam_height_ft": "31",
        },
    }
    (ROOT / "cedar_hollow_drawing.truth.json").write_text(
        json.dumps(truth, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
