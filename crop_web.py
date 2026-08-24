#!/usr/bin/env python3
"""Crop the exported slides to their drawn area and save web-resolution PNGs.

The slide is 20in wide and the artwork rarely fills it, so an uncropped export
is mostly empty ground. Colour is already correct from the deck, so nothing is
repainted here.
"""
import numpy as np, os
from PIL import Image
from scipy import ndimage
Image.MAX_IMAGE_PIXELS = None

BG = np.array([13, 18, 14])
DST = "/Users/chenyuecai/gloss-page/v2/assets/img"
MAX_W = 3200        # ~2.9x the 1120px column: sharp on retina, sane file size

INK = np.array([233, 238, 234])       # --ink


def knockout_glyph_plates(a):
    """Drop the white plate out from behind pasted LaTeX labels.

    The loss labels are pictures, not text, so the deck pass cannot reach them
    and they read as small white boxes on the dark ground. They are safe to
    identify precisely: a white island that encloses NEUTRAL dark marks and no
    colour at all, filling nearly all of its bounding box. A render or a mask
    tile always carries some colour, or no dark content, or is not a rectangle,
    so none of them match - which keeps the standing rule about not touching
    image content intact. The rectangle test also keeps the retoned step
    markers out: a plate fills 1.00 of its box, a disc 0.785.
    """
    lum = a.mean(axis=2)
    sat = a.max(axis=2) - a.min(axis=2)
    white = (lum >= 225) & (sat <= 26)
    lab, n = ndimage.label(white)
    if not n:
        return a, 0
    out = a.copy()
    hit = 0
    H, W = lum.shape
    PAD = 4
    for i, tight in enumerate(ndimage.find_objects(lab), start=1):
        comp = lab[tight] == i
        area = int(comp.sum())
        if not (600 <= area <= 60000):
            continue
        inner = ~comp
        if not inner.any():
            continue
        sub = a[tight]
        colour = float((sub.max(axis=2) - sub.min(axis=2))[inner].mean())
        dark = float((sub.mean(axis=2)[inner] < 120).mean())
        if colour >= 8 or dark <= 0.35:
            continue
        h, w = comp.shape
        if ndimage.binary_fill_holes(comp).sum() / float(w * h) < 0.92:
            continue

        # The plate's antialiased rim falls short of 225, so it sits OUTSIDE
        # the white component's own bounding box. Writing only within that box
        # leaves the rim behind as a grey border - invisible against white, a
        # drawn box against the page ground. Work in a padded window so the rim
        # is reachable at all.
        sl = (slice(max(tight[0].start - PAD, 0), min(tight[0].stop + PAD, H)),
              slice(max(tight[1].start - PAD, 0), min(tight[1].stop + PAD, W)))
        comp = lab[sl] == i
        sub = a[sl]
        region = ndimage.binary_fill_holes(comp)

        # Antialiased glyph edges need partial ink, and the rim sits at the
        # same mid luminance, so value cannot separate them - position can.
        # Glyph edges are interior; the rim is the boundary.
        k = np.clip((240 - lum[sl]) / 180.0, 0, 1)[..., None]
        core = ndimage.binary_erosion(region, np.ones((3, 3)), iterations=2)
        out[sl] = np.where(core[..., None], BG * (1 - k) + INK * k, out[sl])

        # Everything from just inside the boundary to just outside it goes to
        # the ground, but only where it is neutral: coloured pixels out there
        # belong to a neighbouring mark - the loss arrows touch these plates -
        # and keep their tips.
        outer = ndimage.binary_dilation(region, np.ones((3, 3)), iterations=PAD)
        neutral = (sub.max(axis=2) - sub.min(axis=2)) <= 40
        out[sl] = np.where(((outer & ~core) & neutral)[..., None], BG, out[sl])
        hit += 1
    return out, hit


def crop_and_save(src, name):
    im = Image.open(src).convert("RGB")
    a = np.asarray(im).astype(np.int16)
    # Both the page ground and pure black count as empty: slide 21 sits its
    # grids on black, and treating that as content kept a large dead band.
    ink = (np.abs(a - BG).max(axis=2) > 14) & (a.max(axis=2) > 26)

    # A single stray column or row - pdftoppm leaves a 1px grey page edge -
    # is enough to stretch a min/max bbox back to the full slide. Require a row
    # or column to carry a real share of ink before it counts as content.
    # A density test alone cannot catch that edge: the line is full height, so
    # its column is as dense as any real one. Eroding first drops every
    # hairline and leaves real strokes standing, which also reclaims the dead
    # band the edge leaves down the right-hand side.
    solid = ndimage.binary_erosion(ink, np.ones((3, 3)))
    if solid.any():
        ink = solid
    col = ink.mean(axis=0)
    row = ink.mean(axis=1)
    tc = max(col.max() * 0.02, 0.004)
    tr = max(row.max() * 0.02, 0.004)
    xs = np.where(col > tc)[0]
    ys = np.where(row > tr)[0]
    if not len(xs) or not len(ys):
        xs = np.where(col > 0)[0]; ys = np.where(row > 0)[0]
    pad = 26
    box = (max(xs.min()-pad, 0), max(ys.min()-pad, 0),
           min(xs.max()+pad, a.shape[1]-1), min(ys.max()+pad, a.shape[0]-1))
    im = im.crop((box[0], box[1], box[2]+1, box[3]+1))
    if im.size[0] > MAX_W:
        im = im.resize((MAX_W, round(MAX_W * im.size[1] / im.size[0])), Image.LANCZOS)
    arr, plates = knockout_glyph_plates(np.asarray(im).astype(np.float32))
    if plates:
        print(f"    ({plates} pasted label plate(s) knocked out)")
        im = Image.fromarray(arr.round().clip(0, 255).astype(np.uint8))
    out = os.path.join(DST, name)
    im.save(out, optimize=True)
    print(f"  {name:26s} {im.size}  {os.path.getsize(out)/1e6:.2f} MB")

for src, name in [("src_data.png",  "fig_data_slide.png"),
                  ("src_model.png", "fig_model_slide.png"),
                  ("src_attn.png",  "fig_attention_slide.png")]:
    crop_and_save(src, name)
