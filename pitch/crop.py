"""Crop pitch screenshots (2400x1500 captures) into slide-ready regions.

Usage: python -I pitch/crop.py <shots_dir>
Prints JSON {name: [width, height]} for the crops it wrote.
"""
import json
import sys
from pathlib import Path

from PIL import Image

# name: (source file, (left, top, right, bottom)) in original pixels
CROPS = {
    "overview_top": ("overview.png", (348, 216, 2380, 1070)),
    "overview_hero": ("overview.png", (366, 372, 1872, 720)),
    "overview_queue": ("overview.png", (372, 898, 2370, 1058)),
    "inspector_calc": ("inspector-calc.png", (1610, 422, 2358, 1368)),
    "scope_pdf": ("scope-ambiguity.png", (1610, 422, 2358, 1380)),
    "scenarios": ("scenarios.png", (360, 216, 2376, 1404)),
    "analytics": ("analytics.png", (360, 396, 2376, 1368)),
    "workspace": ("workspace.png", (360, 120, 1872, 756)),
    "assistant": ("assistant.png", (1766, 434, 2364, 1362)),
    "login": ("login.png", (466, 292, 1934, 1207)),
}

shots = Path(sys.argv[1])
out = shots / "crops"
out.mkdir(exist_ok=True)
sizes = {}
for name, (src, box) in CROPS.items():
    path = shots / src
    if not path.exists():
        continue
    img = Image.open(path).convert("RGB").crop(box)
    img.save(out / f"{name}.png", optimize=True)
    sizes[name] = list(img.size)
print(json.dumps(sizes))
