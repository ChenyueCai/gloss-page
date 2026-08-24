#!/usr/bin/env python3
"""Build the web 3D assets for the GLOSS asset-library section.

Every viewer on the page loads geometry once and swaps only image maps at
runtime, so this script's job is: (a) bake each mesh into a small GLB that
keeps its normal map -- the surface detail lives there, not in the low-poly
geometry -- and (b) emit the GLOSS result maps as webp at web sizes.

Run:  python3 build-assets.py [section ...]     (default: all)
"""
import json, os, shutil, struct, subprocess, sys

import numpy as np
import trimesh
from PIL import Image
from scipy import ndimage

Image.MAX_IMAGE_PIXELS = None

GLOSS = "/Users/chenyuecai/Desktop/workspace/GLOSS"
OUT   = os.path.dirname(os.path.abspath(__file__))
TEX   = f"{OUT}/assets/tex"
MODEL = f"{OUT}/assets/models"
IMG   = f"{OUT}/assets/img"
TMP   = "/Users/chenyuecai/.claude/jobs/d21ae8a3/tmp/build"

MESH = {
    "dragon":   f"{GLOSS}/interactive/data/mesh/dragon_head_1/scene.gltf",
    "bigleaf":  f"{GLOSS}/interactive/data/mesh/big_leaf_1/scene.gltf",
    "lizard":   f"{GLOSS}/interactive/data/mesh/red_lizard/scene.gltf",
    "cabbage":  f"{GLOSS}/assets/data/meshes/gltf/cabbage/scene.gltf",
    "tortoise": f"{GLOSS}/assets/data/meshes/gltf/desert_tortoise/scene.gltf",
    "gourd":    f"{GLOSS}/assets/data/meshes/gltf/gourd/scene.gltf",
}

for d in (TEX, MODEL, IMG, TMP):
    os.makedirs(d, exist_ok=True)


# ---------------------------------------------------------------- textures --
def dilate_uv(im, iters=24):
    """Bleed texel colour outward into the empty UV gutters.

    Charts are packed with black (or transparent) space between them; without
    this, bilinear filtering pulls that void in and every chart edge renders as
    a dark seam. A single nearest-valid-texel pass fills the whole gutter.
    """
    rgb = np.asarray(im.convert("RGB"))
    if im.mode == "RGBA":
        valid = np.asarray(im.split()[-1]) > 8
    else:
        valid = rgb.max(axis=2) > 10
    if valid.all() or not valid.any():
        return Image.fromarray(rgb)
    # distance_transform_edt on the *empty* side hands back, for each empty
    # texel, the index of the closest filled one -- an exact gutter fill.
    idx = ndimage.distance_transform_edt(~valid, return_distances=False,
                                         return_indices=True)
    return Image.fromarray(rgb[tuple(idx)])


def load_map(path, dilate=False, size=None):
    im = Image.open(path)
    if dilate:
        im = dilate_uv(im)
    im = im.convert("RGB")
    if size and im.size[0] != size:
        im = im.resize((size, size), Image.LANCZOS)
    return im


def save_webp(im, name, quality=88):
    p = f"{TEX}/{name}.webp"
    im.save(p, "WEBP", quality=quality, method=5)
    print(f"    tex {name}.webp {im.size[0]}px {os.path.getsize(p)//1024}KB")
    return p


def pack_orm(metallic, roughness, size):
    """glTF wants one image with roughness in G and metallic in B."""
    m = load_map(metallic, size=size).convert("L")
    r = load_map(roughness, size=size).convert("L")
    z = Image.new("L", m.size, 0)
    return Image.merge("RGB", (z, r, m))


# -------------------------------------------------------------------- GLBs --
def mesh_parts(path):
    sc = trimesh.load(path, process=False)
    return list(sc.geometry.values()) if isinstance(sc, trimesh.Scene) else [sc]


def source_normal(path):
    """Reuse the shape's own normal map -- the bumps that GLOSS conditions on."""
    for g in mesh_parts(path):
        n = getattr(g.visual.material, "normalTexture", None)
        if n is not None:
            return n.convert("RGB")
    return None


def build_glb(key, out, albedo, normal_size=2048, orm=None,
              metallic=1.0, roughness=1.0, recentre=True):
    """One mesh, one material: GLOSS albedo + the mesh's own normal map."""
    src = MESH[key]
    parts = mesh_parts(src)
    nrm = source_normal(src)
    if nrm is not None and nrm.size[0] > normal_size:
        nrm = nrm.resize((normal_size, normal_size), Image.LANCZOS)

    mat = trimesh.visual.material.PBRMaterial(
        name=key, baseColorTexture=albedo, normalTexture=nrm,
        metallicRoughnessTexture=orm,
        metallicFactor=metallic, roughnessFactor=roughness, doubleSided=True)

    V, F, UV = [], [], []
    off = 0
    for g in parts:
        V.append(np.asarray(g.vertices)); F.append(np.asarray(g.faces) + off)
        UV.append(np.asarray(g.visual.uv)); off += len(g.vertices)
    V, F, UV = np.vstack(V), np.vstack(F), np.vstack(UV)

    m = trimesh.Trimesh(vertices=V, faces=F, process=False,
                        visual=trimesh.visual.TextureVisuals(
                            uv=UV, material=mat))
    if recentre:
        m.apply_translation(-m.bounding_box.centroid)
        m.apply_scale(1.0 / max(m.extents))
    raw = f"{TMP}/{os.path.basename(out)}"
    m.export(raw, include_normals=True)
    return optimise(raw, out)


def build_grid(key, out, albedos, cols=4, gap=1.18, normal_size=1024):
    """N copies of one shape, one texture each, laid out for side-by-side reading.

    The copies are written as separate glTF meshes, then `gltf-transform dedup`
    collapses their identical position/normal/uv accessors back to a single
    buffer -- so the geometry is paid for once no matter how many tiles.
    """
    src = MESH[key]
    parts = mesh_parts(src)
    nrm = source_normal(src)
    if nrm is not None and nrm.size[0] > normal_size:
        nrm = nrm.resize((normal_size, normal_size), Image.LANCZOS)

    V, F, UV, off = [], [], [], 0
    for g in parts:
        V.append(np.asarray(g.vertices)); F.append(np.asarray(g.faces) + off)
        UV.append(np.asarray(g.visual.uv)); off += len(g.vertices)
    V, F, UV = np.vstack(V), np.vstack(F), np.vstack(UV)
    V = V - V.mean(axis=0)
    V = V / max(V.max(axis=0) - V.min(axis=0))

    rows = (len(albedos) + cols - 1) // cols
    scene = trimesh.Scene()
    for i, alb in enumerate(albedos):
        mat = trimesh.visual.material.PBRMaterial(
            name=f"{key}_{i:02d}", baseColorTexture=alb, normalTexture=nrm,
            metallicFactor=0.0, roughnessFactor=0.72, doubleSided=True)
        m = trimesh.Trimesh(vertices=V.copy(), faces=F, process=False,
                            visual=trimesh.visual.TextureVisuals(
                                uv=UV, material=mat))
        x = ((i % cols) - (cols - 1) / 2) * gap
        y = ((rows - 1) / 2 - (i // cols)) * gap
        T = np.eye(4); T[:3, 3] = [x, y, 0.0]
        scene.add_geometry(m, node_name=f"tile{i:02d}", transform=T)
    raw = f"{TMP}/{os.path.basename(out)}"
    scene.export(raw, include_normals=True)
    return optimise(raw, out, dedup=True)


def optimise(raw, out, dedup=False):
    """webp-compress textures and Draco-compress geometry.

    --simplify false is mandatory: the default decimates the mesh, which throws
    away exactly the surface detail these results are about.
    """
    cmd = ["npx", "-y", "@gltf-transform/cli@4.1.1", "optimize", raw, out,
           "--texture-compress", "webp", "--compress", "draco",
           "--simplify", "false"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out):
        print("    gltf-transform failed, shipping uncompressed\n", r.stderr[-800:])
        shutil.copy(raw, out)
    print(f"    glb {os.path.basename(out)} "
          f"{os.path.getsize(raw)//1024}KB -> {os.path.getsize(out)//1024}KB")
    return out


# ==========================================================================
# 4.1 Blending -- several shapes, several reference brushes each
# ==========================================================================
BLEND = {
    "dragon": dict(mesh="dragon", size=2048, refs=[
        ("blend_dragon_a", f"{GLOSS}/interactive/results/dragon_head-4k/texture_blended_dilated.png", False),
        ("blend_dragon_b", f"{GLOSS}/interactive/results/dragon_head-4k/texture-1_blended_dilated.png", False),
    ]),
    "bigleaf": dict(mesh="bigleaf", size=2048, refs=[
        ("blend_leaf_a", f"{GLOSS}/interactive/results/big_leaf-4k/texture.png",   True),
        ("blend_leaf_b", f"{GLOSS}/interactive/results/big_leaf-4k/texture-1.png", True),
        ("blend_leaf_c", f"{GLOSS}/interactive/results/big_leaf-4k/texture-2.png", True),
        ("blend_leaf_d", f"{GLOSS}/interactive/results/big_leaf-4k/texture-4.png", True),
    ]),
    "lizard": dict(mesh="lizard", size=2048, refs=[
        ("blend_lizard_a", f"{GLOSS}/interactive/results/red_lizard/red_lizard_pnt.paint.png",   True),
        ("blend_lizard_b", f"{GLOSS}/interactive/results/red_lizard/red_lizard_pnt.paint.1.png", True),
    ]),
}


def do_blending():
    for name, spec in BLEND.items():
        print(f"[blend] {name}")
        first = None
        for out, src, dil in spec["refs"]:
            im = load_map(src, dilate=dil, size=spec["size"])
            save_webp(im, out)
            thumb = im.resize((256, 256), Image.LANCZOS)
            thumb.save(f"{IMG}/th_{out}.webp", "WEBP", quality=80)
            first = first or im
        build_glb(spec["mesh"], f"{MODEL}/{name}.glb", first,
                  metallic=0.0, roughness=0.62)


# ==========================================================================
# 4.2 PBR -- same shape, three generated materials, judged under moving light
# ==========================================================================
CAB = f"{GLOSS}/assets/results/materials/cabbage"
PBR_SETS = [
    ("pbr_cab_teal",  f"{CAB}/view0151.basecolor.png",
     f"{CAB}/texture-151.metallic.png", f"{CAB}/texture-151.roughness.png"),
    ("pbr_cab_gold",  f"{CAB}/view0166.basecolor.png",
     f"{CAB}/texture-166.metallic.png", f"{CAB}/texture-166.roughness.png"),
    ("pbr_cab_green", f"{CAB}/view0258.basecolor.png",
     f"{CAB}/texture-258.metallic.png", f"{CAB}/texture-258.roughness.png"),
]


def do_pbr():
    print("[pbr] cabbage")
    first_alb = first_orm = None
    for name, alb, met, rgh in PBR_SETS:
        a = load_map(alb, dilate=True, size=1536)
        save_webp(a, name)
        a.resize((256, 256), Image.LANCZOS).save(f"{IMG}/th_{name}.webp", "WEBP", quality=80)
        o = pack_orm(met, rgh, 1024)
        save_webp(o, name + "_orm", quality=82)
        # a flat mid-roughness stand-in, so the page can show what the generated
        # metallic/roughness actually buys over albedo alone
        first_alb = first_alb or a
        first_orm = first_orm or o
    flat = Image.new("RGB", (16, 16), (0, 190, 0))     # roughness .75, metal 0
    save_webp(flat, "pbr_cab_flat_orm", quality=90)
    build_glb("cabbage", f"{MODEL}/cabbage_pbr.glb", first_alb, orm=first_orm,
              metallic=1.0, roughness=1.0)


# ==========================================================================
# 4.3 Zero-shot transfer -- G_M trained on M, applied to an unseen N
# ==========================================================================
def split_panels(path, out_prefix, labels, label_band=90):
    """Cut a paper strip figure into its labelled panels.

    The panels themselves touch (callout boxes overhang into their neighbours),
    but the caption words underneath do not -- so the word clusters in the
    label band, not gaps in the artwork, decide where one panel ends.
    """
    im = Image.open(path).convert("RGB")
    W, H = im.size
    band = np.asarray(im.convert("L").crop((0, H - label_band, W, H)))
    ink = (band < 160).any(axis=0)
    words, run = [], None
    for x in range(W + 1):
        on = ink[x] if x < W else False
        if on and run is None:
            run = [x, x]
        elif on:
            run[1] = x
        elif run is not None:
            if words and run[0] - words[-1][1] < 40:   # letter/word spacing
                words[-1][1] = run[1]
            else:
                words.append(run)
            run = None
    if len(words) != len(labels):
        print(f"    !! {os.path.basename(path)}: found {len(words)} captions, "
              f"expected {len(labels)} -- skipped")
        return
    cuts = [0] + [(words[i][1] + words[i + 1][0]) // 2
                  for i in range(len(words) - 1)] + [W]
    for i, lab in enumerate(labels):
        if not lab:
            continue
        crop = im.crop((cuts[i], 0, cuts[i + 1], H - label_band))
        crop.thumbnail((820, 820), Image.LANCZOS)
        q = f"{IMG}/{out_prefix}_{lab}.webp"
        crop.save(q, "WEBP", quality=88)
        print(f"    img {os.path.basename(q)} {crop.size}")


PAPER = os.path.expanduser("~/Downloads/GLOSS_camera_ready_BACKUP_2026-08-23/img/transfer")
TRANSFER_TEX = f"{GLOSS}/assets/results/transfer"


def do_transfer():
    print("[transfer] tortoise")
    for out, src in [("tr_tortoise_a", f"{TRANSFER_TEX}/tortoise/texture-1.png"),
                     ("tr_tortoise_b", f"{TRANSFER_TEX}/tortoise/texture.png")]:
        im = load_map(src, dilate=True, size=1536)
        save_webp(im, out)
        im.resize((256, 256), Image.LANCZOS).save(f"{IMG}/th_{out}.webp", "WEBP", quality=80)
    build_glb("tortoise", f"{MODEL}/tortoise.glb",
              load_map(f"{TRANSFER_TEX}/tortoise/texture-1.png", dilate=True, size=1536),
              metallic=0.0, roughness=0.68)

    labels = ["source", "target", "refs", "infer", "done"]
    for fig, pre in [("fig/brown-tortoise.png", "trp_tortoise"),
                     ("fig/strawberry-bread-transfer.png", "trp_bread")]:
        p = f"{PAPER}/{fig}"
        if os.path.exists(p):
            split_panels(p, pre, labels)
        else:
            print("    missing", p)


# ==========================================================================
# 4.4 Automatic texturing -- one geometry, many references, one viewer
# ==========================================================================
AUTO_SRC  = f"{GLOSS}/assets/results/material-superres-final-test/gourd"
AUTO_COND = f"{GLOSS}/assets/results/test_cond_views/gourd"
AUTO_VIEWS = [0, 1, 2, 3, 5, 6, 7, 9, 10, 11, 13, 14]


def do_auto():
    print("[auto] gourd grid")
    albedos = []
    for v in AUTO_VIEWS:
        im = load_map(f"{AUTO_SRC}/view{v:04d}.png", dilate=True, size=768)
        albedos.append(im)
        c = Image.open(f"{AUTO_COND}/view{v:04d}.basecolor.png").convert("RGB")
        c.thumbnail((192, 192), Image.LANCZOS)
        c.save(f"{IMG}/th_auto_gourd{v:04d}.webp", "WEBP", quality=82)
    build_grid("gourd", f"{MODEL}/gourd_grid.glb", albedos, cols=4)

    # single large gourd, so a chosen look can be inspected close up
    build_glb("gourd", f"{MODEL}/gourd.glb",
              load_map(f"{AUTO_SRC}/view0007.png", dilate=True, size=1536),
              metallic=0.0, roughness=0.7)
    for v in AUTO_VIEWS:
        save_webp(load_map(f"{AUTO_SRC}/view{v:04d}.png", dilate=True, size=1024),
                  f"auto_gourd{v:04d}")


# ==========================================================================
# Normal maps, exported as their own textures so a viewer can show the bare
# geometry the model conditions on next to the texture it generated
# ==========================================================================
NORMAL_OF = {"dragon": "dragon", "bigleaf": "bigleaf", "tortoise": "tortoise",
             "gourd": "gourd", "cabbage": "cabbage"}


def do_normals():
    print("[normals]")
    for key in NORMAL_OF:
        nrm = source_normal(MESH[key])
        if nrm is None:
            print(f"    {key}: no normal map on the source mesh -- skipped")
            continue
        if nrm.size[0] > 1536:
            nrm = nrm.resize((1536, 1536), Image.LANCZOS)
        save_webp(nrm, f"nrm_{key}", quality=90)


SECTIONS = {"normals": do_normals, "blending": do_blending, "pbr": do_pbr,
            "transfer": do_transfer, "auto": do_auto}

if __name__ == "__main__":
    want = sys.argv[1:] or list(SECTIONS)
    for s in want:
        if s not in SECTIONS:
            sys.exit(f"unknown section {s}; pick from {list(SECTIONS)}")
        SECTIONS[s]()
    print("done")
