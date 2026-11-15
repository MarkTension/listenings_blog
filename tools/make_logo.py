# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow", "numpy", "scipy"]
# ///
"""
One-off generator for static/images/logo.svg (the animated header logo).

Reads the dots from static/images/listenings_logo.webp. The top word stays static.
The bottom word gets FRAMES variations where dots jitter to nearby grid spots;
the SVG cycles through them at --fps frames per second (default 2) with plain CSS (no JavaScript).

    uv run tools/make_logo.py            # regenerate with defaults
    uv run tools/make_logo.py --seed 7   # a different random jitter
    uv run tools/make_logo.py --top 0 --bottom 0.9   # still at the top, wild at the bottom
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
ap.add_argument("--fps", type=float, default=2)
ap.add_argument("--seed", type=int, default=1)
ap.add_argument("--top", type=float, default=0.03, help="chance a dot in the top row moves per frame")
ap.add_argument("--bottom", type=float, default=0.8, help="chance a dot in the bottom row moves per frame")
ap.add_argument("--curve", type=float, default=2.0, help="how fast it ramps from top to bottom (1 = linear)")
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
max_c = max(c for c, _ in base)

rng = random.Random(args.seed)
steps = [(-2, 0), (2, 0), (0, -1), (0, 1), (-1, -1), (1, -1), (-1, 1), (1, 1)]

def frame():
    taken, out = set(), []
    def free(c, r):  # dots are wider than a half column: keep neighbours apart
        return 0 <= r <= 7 and 0 <= c <= max_c and not ({(c - 1, r), (c, r), (c + 1, r)} & taken)
    # top rows first, so their (mostly still) dots keep their spot
    for c, r in sorted(rng.sample(base, len(base)), key=lambda d: d[1]):
        spot = (c, r)
        chance = args.top + (args.bottom - args.top) * (r / 7) ** args.curve
        if rng.random() < chance:
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
frames = "\n".join(f'<path class="f" style="animation-delay:{i / args.fps:g}s" d="{path(frame())}"/>' for i in range(n))
svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" fill="{color}">
<style>
.f{{opacity:0;animation:blink {n / args.fps:g}s step-end infinite}}
@keyframes blink{{0%{{opacity:1}}{100 / n:.3f}%,100%{{opacity:0}}}}
@media (prefers-reduced-motion:reduce){{.f{{animation:none}}.f:first-of-type{{opacity:1}}}}
</style>
<path d="{path(top)}"/>
{frames}
</svg>
"""
OUT.write_text(svg)
print(f"wrote {OUT.relative_to(ROOT)}: {len(top)} static dots, {len(bottom)} animated dots x {n} frames, {len(svg)} bytes")
