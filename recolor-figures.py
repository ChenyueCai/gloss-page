#!/usr/bin/env python3
"""Move the section 3.2 paper figures onto the page palette.

Both figures are exported from the paper on a white sheet with navy ink. The
renders, texture patches and attention maps inside them are data and must not
be touched, so neither figure is inverted wholesale:

  * fig_inference is vector-clean, so every diagram pixel lies on a straight
    line between two of six known colours. Those pixels keep their blend
    position and get new endpoints; everything else is a render and is left
    alone. Flow becomes --accent (structure), the GLOSS block and the face
    selection become --accent-2 (emphasis), labels become --ink.
  * fig_attention is a JPEG image grid in a paper margin; only the margin and
    its labels flip.

Both are written RGBA with the sheet knocked out, like fig_data_dark.png, so
they composite onto whatever ground the section uses.

Usage:  python3 recolor-figures.py
"""
import itertools
import os

import numpy as np
from PIL import Image
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "figures-src")
IMG = os.path.join(HERE, "assets", "img")

# ---- page palette ---------------------------------------------------------
BG = np.array([13, 18, 14], np.float32)        # --bg, what alpha is cut against
INK = (233, 238, 234)                          # --ink
GREEN = (93, 203, 129)                         # --accent
ORANGE = (246, 151, 70)                        # --accent-2
PANEL_G = (21, 42, 29)                         # automatic panel, green-tinted
PANEL_O = (45, 33, 24)                         # interactive panel, orange-tinted


def unpremultiply(rgb, alpha):
    """rgb was mixed against BG; recover the colour that alpha carries."""
    a = np.clip(alpha, 0, 1)[..., None]
    out = np.where(a > 0.02, (rgb - BG * (1 - a)) / np.maximum(a, 1e-6), BG)
    return np.concatenate([np.clip(out, 0, 255),
                           np.clip(alpha * 255, 0, 255)[..., None]], axis=2)


def inference(src, dst):
    # the figure is vector-clean, so these six are exact
    pal = {
        'W': (255, 255, 255),   # sheet
        'N': (5, 85, 121),      # ink: labels, outlines, step circles
        'A': (167, 209, 228),   # flow arrows AND both panel fills
        'C': (73, 179, 222),    # the brighter arrow inside the blue panel
        'P': (238, 202, 232),   # interactive panel fill
        'M': (230, 50, 187),    # emphasis: selection, GLOSS block, its arrow
    }
    dstpal = {'W': tuple(BG.astype(int)), 'N': INK, 'A': GREEN,
              'C': GREEN, 'P': ORANGE, 'M': ORANGE}
    tol = 6.0          # max distance to a two-colour blend line
    min_block = 150    # smallest unmatched blob that counts as a render

    a = np.array(Image.open(src).convert('RGB')).astype(np.float32)
    H, W, _ = a.shape
    keys = list(pal)

    # 1. every diagram pixel sits on a line between two palette colours
    best = np.full((H, W), 1e9, np.float32)
    best_t = np.zeros((H, W), np.float32)
    k1 = np.zeros((H, W), np.int8)
    k2 = np.zeros((H, W), np.int8)
    for i1, i2 in itertools.combinations(range(len(keys)), 2):
        c1 = np.array(pal[keys[i1]], np.float32)
        c2 = np.array(pal[keys[i2]], np.float32)
        d = c2 - c1
        t = np.clip(((a - c1) @ d) / float(d @ d), 0, 1)
        dist = np.linalg.norm(a - (c1 + t[..., None] * d), axis=2)
        win = dist < best
        best, best_t = np.where(win, dist, best), np.where(win, t, best_t)
        k1, k2 = np.where(win, i1, k1), np.where(win, i2, k2)

    # antialiasing rings slightly off the pure colours; forgive that near every
    # endpoint except white, where a loose radius would swallow render detail
    endpoint = np.full((H, W), 1e9, np.float32)
    for k in ('N', 'A', 'C', 'P', 'M'):
        endpoint = np.minimum(
            endpoint, np.linalg.norm(a - np.array(pal[k], np.float32), axis=2))
    matched = (best < tol) | (endpoint < 14.0)

    # 2. renders, texture sheets and the patch grid are protected wholesale
    blocks = ndimage.binary_fill_holes(
        ndimage.binary_closing(~matched, np.ones((5, 5))))
    lab, n = ndimage.label(blocks)
    sizes = ndimage.sum(blocks, lab, range(1, n + 1))
    keep = np.zeros(n + 1, bool)
    keep[1:] = sizes >= min_block
    protect = keep[lab]

    # 3. the panel fills share the arrow colour; split them by connectivity
    def panel_of(colour):
        m = np.linalg.norm(a - np.array(colour, np.float32), axis=2) < 12
        l, k = ndimage.label(m)
        if k == 0:
            return np.zeros((H, W), bool)
        s = ndimage.sum(m, l, range(1, k + 1))
        big = l == (int(np.argmax(s)) + 1)
        # fill first, so counters inside the panel (step circles, letter holes)
        # take the panel fill rather than the bright accent
        return ndimage.binary_dilation(ndimage.binary_fill_holes(big),
                                       np.ones((7, 7)))

    panel_blue, panel_pink = panel_of(pal['A']), panel_of(pal['P'])
    tgt = {k: np.broadcast_to(np.array(dstpal[k], np.float32), (H, W, 3)).copy()
           for k in keys}
    tgt['A'][panel_blue] = PANEL_G
    tgt['P'][panel_pink] = PANEL_O

    # 4. remap: keep the blend position, swap the endpoints
    flat = np.stack([tgt[k] for k in keys]).reshape(len(keys), H * W, 3)
    idx = np.arange(H * W)
    c1, c2 = flat[k1.ravel(), idx], flat[k2.ravel(), idx]
    out = (c1 + best_t.ravel()[:, None] * (c2 - c1)).reshape(H, W, 3)
    recol = matched & ~protect
    out = np.where(recol[..., None], out, a)

    # how much of each pixel is sheet, and so how much of it drops out
    w = keys.index('W')
    wht = np.where(k1 == w, 1 - best_t, np.where(k2 == w, best_t, 0.0))
    alpha = np.where(recol, 1 - wht, 1.0)

    # 5. kill the white halo the renders carry from their old sheet
    near = ndimage.binary_dilation(protect, np.ones((9, 9))) & ~protect
    lum = a @ np.array([0.299, 0.587, 0.114], np.float32)
    halo = near & ~matched & (lum > 195)
    k = np.clip((lum - 195) / 55.0, 0, 1)
    out = np.where(halo[..., None], BG * k[..., None] + a * (1 - k[..., None]), out)
    alpha = np.where(halo, 1 - k, alpha)

    # 6. the face selection inside the renders is UI, not data: it is the one
    #    protected colour that still has to move onto the page palette
    hsv = np.array(Image.fromarray(a.astype(np.uint8)).convert('HSV'), np.float32)
    h, sat = hsv[..., 0] * 360 / 255, hsv[..., 1] / 255
    pink = (panel_pink & protect & (sat > 0.12)
            & (((h > 275) & (h < 355)) | (h < 8)))
    hsv[..., 0] = np.where(pink, 26 * 255 / 360, hsv[..., 0])
    shifted = np.array(Image.fromarray(hsv.astype(np.uint8), 'HSV').convert('RGB'),
                       np.float32)
    out = np.where(pink[..., None], shifted, out)

    Image.fromarray(unpremultiply(out, alpha).astype(np.uint8), 'RGBA').save(dst)
    print('wrote %s  (%.0f%% of the sheet dropped out)'
          % (os.path.basename(dst), 100 * (alpha < 0.02).mean()))


def attention(src, dst):
    a = np.array(Image.open(src).convert('RGB')).astype(np.float32)
    H, W, _ = a.shape

    # the two grids are the only full-width dense bands; labels and title are not
    content = a.min(axis=2) < 205
    rows = np.where(content.mean(1) > 0.6)[0]
    cols = np.where(content.mean(0) > 0.6)[0]
    segs, start = [], rows[0]
    for i, r in enumerate(rows[1:], 1):
        if r - rows[i - 1] > 5:
            segs.append((start, rows[i - 1]))
            start = r
    segs.append((start, rows[-1]))
    protect = np.zeros((H, W), bool)
    for y0, y1 in segs:
        protect[y0:y1 + 1, cols.min():cols.max() + 1] = True

    lum = (a @ np.array([0.299, 0.587, 0.114], np.float32)) / 255.0
    k = np.clip((lum - 0.06) / 0.88, 0, 1)          # 1 = sheet, 0 = ink
    out = np.where(protect[..., None],
                   a, BG * k[..., None] + np.array(INK, np.float32) * (1 - k)[..., None])
    alpha = np.where(protect, 1.0, 1 - k)
    Image.fromarray(unpremultiply(out, alpha).astype(np.uint8), 'RGBA').save(dst)
    print('wrote %s  (%d grid bands kept)' % (os.path.basename(dst), len(segs)))


if __name__ == '__main__':
    inference(os.path.join(SRC, 'fig_inference_paper.png'),
              os.path.join(IMG, 'fig_inference_dark.png'))
    attention(os.path.join(SRC, 'fig_attention_paper.jpg'),
              os.path.join(IMG, 'fig_attention_dark.png'))
