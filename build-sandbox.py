#!/usr/bin/env python3
"""Emit sandbox-sized copies of the asset-library assets for the Artifact build.

The artifact sandbox blocks every external host, and Draco's decoder is fetched
from a Google CDN, so geometry here is *quantized* instead -- three.js decodes
KHR_mesh_quantization itself, with nothing to download. Textures are also cut
down, and each single-shape GLB ships a placeholder albedo because app.js
replaces it with the real map the moment the model loads.
"""
import importlib.util, os, shutil, subprocess, sys
from PIL import Image

spec = importlib.util.spec_from_file_location(
    "ba", os.path.join(os.path.dirname(os.path.abspath(__file__)), "build-assets.py"))
ba = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ba)

RAW = "/Users/chenyuecai/.claude/jobs/d08ddf64/tmp/artifact/raw"
TMP = ba.TMP
os.makedirs(RAW, exist_ok=True)

PLACEHOLDER = Image.new("RGB", (16, 16), (170, 170, 170))


def quantise(raw, out):
    cmd = ["npx", "-y", "@gltf-transform/cli@4.1.1", "optimize", raw, out,
           "--texture-compress", "webp", "--compress", "quantize",
           "--simplify", "false"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or not os.path.exists(out):
        print("   quantize failed:", r.stderr[-400:]); shutil.copy(raw, out)
    print(f"   {os.path.basename(out):22s} {os.path.getsize(out)//1024:5d} KB")


def model(key, name, albedo=None, orm=None, normal=1024, metallic=0.0, roughness=0.65):
    print(f"[glb] {name}")
    tmp = f"{TMP}/sb_{name}"
    ba.build_glb.__wrapped__ if False else None
    # reuse the real builder but stop it Draco-compressing, by writing the raw
    # glb ourselves through build_glb's own path then quantizing instead
    src = ba.MESH[key]
    parts = ba.mesh_parts(src)
    nrm = ba.source_normal(src)
    if nrm is not None and nrm.size[0] > normal:
        nrm = nrm.resize((normal, normal), Image.LANCZOS)
    import numpy as np, trimesh
    V, F, UV, off = [], [], [], 0
    for g in parts:
        V.append(np.asarray(g.vertices)); F.append(np.asarray(g.faces) + off)
        UV.append(np.asarray(g.visual.uv)); off += len(g.vertices)
    V, F, UV = np.vstack(V), np.vstack(F), np.vstack(UV)
    mat = trimesh.visual.material.PBRMaterial(
        name=name, baseColorTexture=albedo or PLACEHOLDER, normalTexture=nrm,
        metallicRoughnessTexture=orm, metallicFactor=metallic,
        roughnessFactor=roughness, doubleSided=True)
    m = trimesh.Trimesh(vertices=V, faces=F, process=False,
                        visual=trimesh.visual.TextureVisuals(uv=UV, material=mat))
    m.apply_translation(-m.bounding_box.centroid)
    m.apply_scale(1.0 / max(m.extents))
    m.export(tmp, include_normals=True)
    quantise(tmp, f"{RAW}/{name}")


def grid(name, size=384, cols=4):
    print(f"[glb] {name}")
    albedos = [ba.load_map(f"{ba.AUTO_SRC}/view{v:04d}.png", dilate=True, size=size)
               for v in ba.AUTO_VIEWS]
    tmp = f"{TMP}/sb_{name}"
    import numpy as np, trimesh
    src = ba.MESH["gourd"]
    parts = ba.mesh_parts(src)
    nrm = ba.source_normal(src)
    if nrm is not None and nrm.size[0] > 768:
        nrm = nrm.resize((768, 768), Image.LANCZOS)
    V, F, UV, off = [], [], [], 0
    for g in parts:
        V.append(np.asarray(g.vertices)); F.append(np.asarray(g.faces) + off)
        UV.append(np.asarray(g.visual.uv)); off += len(g.vertices)
    V, F, UV = np.vstack(V), np.vstack(F), np.vstack(UV)
    V = V - V.mean(axis=0); V = V / max(V.max(axis=0) - V.min(axis=0))
    rows = (len(albedos) + cols - 1) // cols
    scene = trimesh.Scene()
    for i, alb in enumerate(albedos):
        mat = trimesh.visual.material.PBRMaterial(
            name=f"t{i:02d}", baseColorTexture=alb, normalTexture=nrm,
            metallicFactor=0.0, roughnessFactor=0.72, doubleSided=True)
        mm = trimesh.Trimesh(vertices=V.copy(), faces=F, process=False,
                             visual=trimesh.visual.TextureVisuals(uv=UV, material=mat))
        T = np.eye(4)
        T[:3, 3] = [((i % cols) - (cols - 1) / 2) * 1.18,
                    ((rows - 1) / 2 - (i // cols)) * 1.18, 0.0]
        scene.add_geometry(mm, node_name=f"tile{i:02d}", transform=T)
    scene.export(tmp, include_normals=True)
    quantise(tmp, f"{RAW}/{name}")


def tex(src_name, out_name, size, quality=80):
    p = f"{ba.TEX}/{src_name}.webp"
    im = Image.open(p).convert("RGB")
    if im.size[0] > size:
        im = im.resize((size, size), Image.LANCZOS)
    q = f"{RAW}/{out_name}.webp"
    im.save(q, "WEBP", quality=quality, method=5)
    return os.path.getsize(q)


if __name__ == "__main__":
    model("dragon",   "dragon.glb",   normal=1024)
    model("bigleaf",  "bigleaf.glb",  normal=1024)
    model("tortoise", "tortoise.glb", normal=1024)
    model("gourd",    "gourd.glb",    normal=1024)
    model("cabbage",  "cabbage_pbr.glb", normal=1024,
          orm=Image.new("RGB", (16, 16), (0, 190, 0)), metallic=1.0, roughness=1.0)
    grid("gourd_grid.glb")

    total = 0
    for n in ("blend_dragon_a", "blend_dragon_b", "blend_leaf_a", "blend_leaf_b",
              "blend_leaf_c", "blend_leaf_d", "tr_tortoise_a", "tr_tortoise_b"):
        total += tex(n, n, 1024)
    for n in ("pbr_cab_teal", "pbr_cab_gold", "pbr_cab_green"):
        total += tex(n, n, 1024)
        total += tex(n + "_orm", n + "_orm", 512, quality=76)
    total += tex("pbr_cab_flat_orm", "pbr_cab_flat_orm", 16, quality=90)
    for n in ("nrm_dragon", "nrm_bigleaf", "nrm_tortoise", "nrm_gourd"):
        total += tex(n, n, 1024, quality=82)
    for v in ba.AUTO_VIEWS:
        total += tex(f"auto_gourd{v:04d}", f"auto_gourd{v:04d}", 512, quality=78)
    print(f"[tex] {total/1e6:.2f} MB")

    n = 0
    for f in os.listdir(ba.IMG):
        if f.startswith(("th_blend_", "th_auto_gourd", "th_tr_", "trp_")):
            im = Image.open(f"{ba.IMG}/{f}").convert("RGB")
            if im.size[0] > 560:
                im.thumbnail((560, 560), Image.LANCZOS)
            im.save(f"{RAW}/{f}", "WEBP", quality=80); n += 1
    print(f"[img] {n} thumbnails and panels")
