# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow", "numpy", "scipy"]
# ///
"""
One-off generator for static/images/logo.svg (the animated header logo).

Reads the dots from static/images/listenings_logo.webp. The top word stays static.
The bottom word gets FRAMES variations where dots jitter to nearby grid spots;
the SVG cycles through them at 1 frame per second with plain CSS (no JavaScript).

    uv run tools/make_logo.py            # regenerate with defaults
    uv run tools/make_logo.py --seed 7   # a different random jitter
"""

import argparse
import random
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).parent.parent
SRC = ROOT / "static/images/listenings_logo.webp"
OUT = ROOT / "static/images/logo.svg"

ap = argparse.ArgumentParser()
ap.add_argument("--frames", type=int, default=8)
ap.add_argument("--seed", type=int, default=1)
ap.add_argument("--move", type=float, default=0.45, help="chance a dot moves in a frame")
args = ap.parse_args()

img = np.array(Image.open(SRC))
h, w = img.shape[:2]
alpha = img[:, :, 3] > 128
color = "#%02x%02x%02x" % tuple(img[alpha][0][:3])

labels, _ = ndimage.label(alpha)
dots = [(s[1].start, s[0].start) for s in ndimage.find_objects(labels)]
size = 31

# Grid: half-column steps horizontally, row steps vertically.
X0, DX, DY = 96, 47.29 / 2, 47.29
mid = h / 2
top = [d for d in dots if d[1] < mid]
bottom = [d for d in dots if d[1] >= mid]
Y0b = min(y for _, y in bottom)

def to_grid(x, y):
    return round((x - X0) / DX), round((y - Y0b) / DY)

def to_px(c, r):
    return round(X0 + c * DX), round(Y0b + r * DY)

base = [to_grid(x, y) for x, y in bottom]
max_c = max(c for c, _ in base) + 2

rng = random.Random(args.seed)
steps = [(-2, 0), (2, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)]

def frame():
    taken, out = set(), []
    def free(c, r):  # dots are wider than a half column: keep neighbours apart
        return 0 <= r <= 7 and 0 <= c <= max_c and not ({(c - 1, r), (c, r), (c + 1, r)} & taken)
    for c, r in rng.sample(base, len(base)):
        spot = (c, r)
        if rng.random() < args.move:
            dc, dr = rng.choice(steps)
            if free(c + dc, r + dr):
                spot = (c + dc, r + dr)
        if not free(*spot):
            continue
        taken.add(spot)
        out.append(to_px(*spot))
    return out

def path(points):
    return "".join(f"M{x} {y}h{size}v{size}h-{size}z" for x, y in sorted(points, key=lambda p: (p[1], p[0])))

n = args.frames
frames = "\n".join(f'<path class="f" style="animation-delay:{i}s" d="{path(frame())}"/>' for i in range(n))
svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" fill="{color}">
<style>
.f{{opacity:0;animation:blink {n}s step-end infinite}}
@keyframes blink{{0%{{opacity:1}}{100 / n:.3f}%,100%{{opacity:0}}}}
@media (prefers-reduced-motion:reduce){{.f{{animation:none}}.f:first-of-type{{opacity:1}}}}
</style>
<path d="{path(top)}"/>
{frames}
</svg>
"""
OUT.write_text(svg)
print(f"wrote {OUT.relative_to(ROOT)}: {len(top)} static dots, {len(bottom)} animated dots x {n} frames, {len(svg)} bytes")
