#!/usr/bin/env python3
"""Swap the live model-viewer widgets in index.html for turntable clips.

Blocks are found by the viewer's id and the enclosing container is matched by
walking the div nesting, so this keeps working while the page around it is
being renumbered and re-ordered.
"""
import os, re, sys

V = os.path.dirname(os.path.abspath(__file__))
SRC = f"{V}/index.html"


def container_span(html, viewer_id, cls):
    """Byte range of the <div class="cls"> that wraps this viewer."""
    at = html.index(f'id="{viewer_id}"')
    start = html.rindex(f'<div class="{cls}"', 0, at)
    i, depth = start, 0
    for m in re.finditer(r"<div\b|</div>", html[start:]):
        depth += 1 if m.group(0) == "<div" else -1
        if depth == 0:
            return start, start + m.end()
    raise SystemExit(f"unbalanced markup around {viewer_id}")


def clip(vid, name, label, extra=""):
    return (f'      <figure class="turntable"{extra}>\n'
            f'        <video id="{vid}" muted loop playsinline preload="none"\n'
            f'               poster="assets/video/{name}.jpg" data-src="assets/video/{name}.mp4"></video>\n'
            f'        <figcaption class="turntable-cap">{label}</figcaption>\n'
            f'      </figure>')


def swatch(vid_name, tag, first=False, maps=""):
    return (f'            <button data-vid="assets/video/{vid_name}.mp4" '
            f'data-poster="assets/video/{vid_name}.jpg" data-cap="{tag}"{maps} '
            f'aria-pressed="{str(first).lower()}">{tag}</button>')


def maps_of(stem):
    """Albedo and packed rough+metal for a PBR look, shown beside the clip."""
    return (f' data-alb="assets/tex/{stem}.webp" data-orm="assets/tex/{stem}_orm.webp"')


BLEND = """<div class="viewer-row">
{clip}
      <aside class="viewer-side">
        <div>
          <div class="side-label">Dragon head &mdash; reference brush</div>
          <div class="seg" id="blendDragon" data-drives="vidBlend">
{d}
          </div>
        </div>
        <div>
          <div class="side-label">Big leaf &mdash; reference brush</div>
          <div class="seg" id="blendLeaf" data-drives="vidBlend">
{l}
          </div>
        </div>
        <p class="hint">Each clip is one full turn of the same mesh. Only the texture differs between them,
          so any two can be compared frame for frame. The normal map shows the geometry every one of them
          had to agree with.</p>
      </aside>
    </div>"""

PBR = """<div class="viewer-row">
{clip}
      <aside class="viewer-side">
        <div>
          <div class="side-label">Generated material</div>
          <div class="seg" id="pbrMats" data-drives="vidPbr">
{m}
          </div>
        </div>
        <p class="hint">The shape is held still and the environment turns around it, so a highlight sweeps the
          surface. Albedo alone cannot tell a waxy leaf from a glazed one &mdash; the sweep is what separates them.</p>
        <div>
          <div class="side-label">Maps behind the current look</div>
          <div class="map-strip" id="pbrMaps"></div>
        </div>
      </aside>
    </div>

    <div class="figure-duo pbr-ab">
      <figure class="turntable small">
        <video muted loop playsinline preload="none" poster="assets/video/tt_pbr_teal.jpg"
               data-src="assets/video/tt_pbr_teal.mp4"></video>
        <figcaption>Albedo <b>+ generated metallic and roughness</b></figcaption>
      </figure>
      <figure class="turntable small">
        <video muted loop playsinline preload="none" poster="assets/video/tt_pbr_teal_flat.jpg"
               data-src="assets/video/tt_pbr_teal_flat.mp4"></video>
        <figcaption>The same albedo, <b>flat material</b></figcaption>
      </figure>
    </div>
    <p class="caption">Identical geometry, identical albedo, identical lighting &mdash; the only difference is
      whether the generated metallic and roughness maps are in play.</p>"""

TRANSFER = """<div class="viewer-row">
{clip}
      <aside class="viewer-side">
        <div>
          <div class="side-label">Result on the unseen tortoise</div>
          <div class="seg" id="transferRefs" data-drives="vidTransfer">
{t}
          </div>
        </div>
        <p class="hint">The scute pattern lands on the tortoise&rsquo;s own domed plates and follows them around
          the legs and neck, because references are chosen by local geometry rather than by position on the
          source. Switch to the normal map to compare against panel 2 above.</p>
      </aside>
    </div>"""

KOI = """<div class="viewer-row">
{clip}
      <aside class="viewer-side">
        <div>
          <div class="side-label">Conditioning reference</div>
          <div class="plate"><img src="assets/img/koi_cond.webp" alt="Single-view reference given to every method"></div>
        </div>
        <div>
          <div class="side-label">Method</div>
          <div class="seg" id="koiMethods" data-drives="vidKoi">
{m}
          </div>
        </div>
        <p class="hint">Every method received exactly this one image. Each clip is the same turn of the same
          mesh, so the comparison is like for like.</p>
      </aside>
    </div>"""

GRID = """<div class="grid-viewer">
{clip}
      <p class="hint centred">One mesh, twelve results &middot; a single turn of the whole set</p>
    </div>"""


def build():
    h = open(SRC).read()

    # --- 4.4 automatic: the single-gourd widget has no still equivalent worth
    # keeping now that the twelve-tile clip covers the same ground.
    a, b = container_span(h, "mvGourd", "viewer-row")
    pre = h.rindex("<h4 class=\"mini-title\">", 0, a)
    h = h[:pre] + h[b:]

    reps = [
        ("mvBlend", "viewer-row", BLEND.format(
            clip=clip("vidBlend", "tt_blend_dragon_a", "Dragon head &middot; Jade &amp; ivory"),
            d="\n".join([swatch("tt_blend_dragon_a", "Jade &amp; ivory", True),
                         swatch("tt_blend_dragon_b", "Ember face"),
                         swatch("tt_blend_dragon_n", "Normal map")]),
            l="\n".join([swatch("tt_blend_leaf_a", "Rose / mint"),
                         swatch("tt_blend_leaf_b", "Mint / amber"),
                         swatch("tt_blend_leaf_c", "Blush"),
                         swatch("tt_blend_leaf_d", "Cobalt / rust"),
                         swatch("tt_blend_leaf_n", "Normal map")]))),
        ("mvPbr", "viewer-row", PBR.format(
            clip=clip("vidPbr", "tt_pbr_teal", "Glazed teal"),
            m="\n".join([swatch("tt_pbr_teal", "Glazed teal", True, maps_of("pbr_cab_teal")),
                         swatch("tt_pbr_gold", "Waxed gold", False, maps_of("pbr_cab_gold")),
                         swatch("tt_pbr_green", "Fresh green", False, maps_of("pbr_cab_green"))]))),
        ("mvTransfer", "viewer-row", TRANSFER.format(
            clip=clip("vidTransfer", "tt_tr_tortoise_a", "Amber scutes"),
            t="\n".join([swatch("tt_tr_tortoise_a", "Amber scutes", True),
                         swatch("tt_tr_tortoise_b", "Red shell"),
                         swatch("tt_tr_tortoise_n", "Normal map")]))),
        ("mvGrid", "grid-viewer", GRID.format(
            clip=clip("vidGrid", "tt_auto_grid", "Twelve references, one gourd mesh"))),
        ("mvKoi", "viewer-row", KOI.format(
            clip=clip("vidKoi", "tt_auto_koi_ours", "GLOSS (ours)"),
            m="\n".join([swatch("tt_auto_koi_ours", "GLOSS (ours)", True),
                         swatch("tt_auto_koi_hunyuan", "Hunyuan 2.1"),
                         swatch("tt_auto_koi_trellis2", "TRELLIS 2"),
                         swatch("tt_auto_koi_mvadapter", "MV-Adapter"),
                         swatch("tt_auto_koi_texgen", "TexGen"),
                         swatch("tt_auto_koi_paint3d", "Paint3D")]))),
    ]
    for vid, cls, new in reps:
        a, b = container_span(h, vid, cls)
        h = h[:a] + new + h[b:]

    # the section lede promised live WebGL
    h = h.replace(
        "Every viewer here is live WebGL &mdash; drag to\n      orbit, scroll to zoom. Geometry loads once per shape; switching a reference or a method only swaps an\n      image map, so comparisons are instant and always on identical geometry.",
        "Every result below is a full turn of the shape, rendered offline. Within a section the mesh, the\n      camera path and the lighting are identical from clip to clip, so what changes between them is only ever\n      the texture.")

    # model-viewer is no longer on the page
    h = re.sub(r'\s*<script type="module" src="vendor/model-viewer\.min\.js"></script>', "", h)
    open(SRC, "w").write(h)
    print("index.html rewritten;", h.count("<model-viewer"), "model-viewer tags remain")


if __name__ == "__main__":
    build()
