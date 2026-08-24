"""Re-tone the data-pipeline figure for a dark page.

White ground becomes transparent, black type becomes light, and the flat
diagram colours are remapped onto the page palette. Photographic content (the
urchin renders, the texture patches) is protected by only touching pixels that
sit in FLAT regions - a photo has local variation, a diagram fill does not.
"""
import numpy as np
from PIL import Image
from scipy import ndimage

SRC = "/Users/chenyuecai/Desktop/data.png"
DST = "/Users/chenyuecai/gloss-page/v2/assets/img/fig_data_dark.png"

INK   = (233, 238, 234)   # --ink
GREEN = ( 93, 203, 129)   # --accent
DEEP  = ( 42, 151,  84)   # --accent-deep
ORANGE= (246, 151,  70)   # --accent-2
OSOFT = (255, 180, 113)   # --accent-2-soft
PANEL = ( 28,  34,  30)   # --panel

# flat diagram colour -> page palette
REMAP = [
    ((0x10, 0x60, 0x80), "TEAL", 88),   # boxes AND the italic stage labels
    ((0x10, 0x60, 0x90), "TEAL", 88),
    ((0xa0, 0xd0, 0xe0), GREEN,  52),   # light blue arrows / outlines
    ((0xd0, 0x60, 0xc0), DEEP,   70),   # magenta GLOSS box
    ((0xf0, 0xf0, 0x10), ORANGE, 70),   # yellow inner box
    ((0xf0, 0xc0, 0xd8), OSOFT,  40),   # pink loss arrows
    ((0xe0, 0xe0, 0xd0), PANEL,  22),   # cream grouping panels
]

im = Image.open(SRC).convert("RGB")
a = np.asarray(im).astype(np.float32)
h, w, _ = a.shape
lum = a.mean(axis=2)
sat = a.max(axis=2) - a.min(axis=2)

# flatness: a photo varies locally, a fill does not
local = ndimage.uniform_filter(lum, 5)
var = ndimage.uniform_filter((lum - local) ** 2, 5)
flat = var < 18

out = a.copy()
alpha = np.full((h, w), 255.0)

# 1. white ground -> transparent (border-connected only, so white inside the
#    mask images and panels survives)
white = (lum >= 232) & (sat <= 18)
lab, n = ndimage.label(white)
edge = set(lab[0, :]) | set(lab[-1, :]) | set(lab[:, 0]) | set(lab[:, -1]); edge.discard(0)
bg = np.isin(lab, list(edge))
soft = np.clip((lum - 214) / (247 - 214), 0, 1) * ndimage.binary_dilation(bg, iterations=1)
# "sits on the page ground" - true for labels and connectors, false for anything
# buried inside a dark panel
near_bg = ndimage.binary_dilation(bg, iterations=26)
alpha = 255.0 * (1 - soft)

# 2. flat diagram fills -> palette.
# The light blue is used for thin arrows and outlines, and it is also close to
# the pale blue-grey of the urchin renders and the normal maps. Distinguishing
# them by colour alone repaints the photographs, so the thin-stroke colours are
# additionally required to BE thin: a component whose distance transform never
# exceeds a few pixels is a stroke, anything fatter is picture content.
THIN_ONLY = {(0xa0, 0xd0, 0xe0), (0xf0, 0xc0, 0xd8)}
MAX_STROKE = 20    # px half-width; arrows are ~30px wide at 3935px
MIN_STROKE_AREA = 150  # skips speckles the colour test picks up inside renders

for src_c, dst_c, tol in REMAP:
    d = np.abs(a - np.array(src_c, dtype=np.float32)).max(axis=2)
    m = (d <= tol) & ~bg
    if dst_c != "TEAL":
        m &= flat
    if dst_c == "TEAL" and m.any():
        # Type and box fills share this colour, and so do parts of the urchin
        # renders. Two tests separate them: the LABELS sit on the white ground,
        # the renders sit deep inside dark panels; and fills are thick where
        # type is thin. Anything failing both is picture content, left alone.
        dist = ndimage.distance_transform_edt(m)
        lab_t, n_t = ndimage.label(m)
        if n_t:
            thickest = ndimage.maximum(dist, lab_t, range(1, n_t + 1))
            on_page = ndimage.maximum(near_bg, lab_t, range(1, n_t + 1))
            thin_ids = [i + 1 for i, (t, o) in enumerate(zip(thickest, on_page))
                        if t <= MAX_STROKE and o]
            thick_ids = [i + 1 for i, (t, o) in enumerate(zip(thickest, on_page))
                         if t > MAX_STROKE and o]
            out[np.isin(lab_t, thin_ids)] = GREEN
            out[np.isin(lab_t, thick_ids) & flat] = DEEP
        continue
    if src_c in THIN_ONLY and m.any():
        dist = ndimage.distance_transform_edt(m)
        lab_m, n_m = ndimage.label(m)
        if n_m:
            thickest = ndimage.maximum(dist, lab_m, range(1, n_m + 1))
            areas = ndimage.sum(m, lab_m, range(1, n_m + 1))
            keep = [i + 1 for i, (t, ar) in enumerate(zip(thickest, areas))
                    if t <= MAX_STROKE and ar >= MIN_STROKE_AREA]
            m = np.isin(lab_m, keep)
    out[m] = dst_c

# 3. black type and thin rules -> light ink (small components only, so the grey
#    mask images keep their own values)
dark = (lum < 150) & (sat <= 45) & ~bg
dl, dn = ndimage.label(dark)
if dn:
    sizes = ndimage.sum(dark, dl, range(1, dn + 1))
    small = np.isin(dl, [i + 1 for i, s in enumerate(sizes) if s < 9000])
    k = np.clip((150 - lum) / 150, 0, 1)[..., None]
    out[small] = ((1 - k) * a + k * np.array(INK, dtype=np.float32))[small]

rgba = np.dstack([out.round(), alpha.round()]).astype(np.uint8)
Image.fromarray(rgba, "RGBA").save(DST)
import os
print("wrote", DST, f"{os.path.getsize(DST)/1e6:.2f} MB", Image.open(DST).size)
