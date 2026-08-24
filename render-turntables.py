#!/usr/bin/env python3
"""Render the asset-library results as looping turntable videos.

The page used to carry live model-viewer widgets; these replace them. Each clip
is a full 360 degrees sampled at a fixed step, so the last frame meets the first
and the loop is seamless. The PBR clips instead hold the shape still and turn
the environment around it -- a roughness or metallic map only shows itself when
the highlight moves.

Frames come from model-viewer's own canvas via toDataURL, so what is captured is
exactly what the page rendered. Run:  python3 render-turntables.py [name ...]
"""
import asyncio, base64, io, os, subprocess, sys
from PIL import Image

V    = os.path.dirname(os.path.abspath(__file__))
OUT  = f"{V}/assets/video"
TMP  = "/Users/chenyuecai/.claude/jobs/d21ae8a3/tmp/turn"
PORT = 8899
W, H, FRAMES, FPS = 900, 560, 64, 20
STAGE = (15, 21, 16)                     # --stage, so clips sit on the page ground

os.makedirs(TMP, exist_ok=True)
os.makedirs(OUT, exist_ok=True)

def T(name, glb, tex, **kw):
    return dict(name=name, glb=glb, tex=tex, mode="turn", **kw)

def L(name, glb, tex, orm):
    return dict(name=name, glb=glb, tex=tex, orm=orm, mode="light",
                phi=74, radius="108%")

SPECS = [
    # 3.1 blending -- two shapes, several reference brushes each
    T("tt_blend_dragon_a", "dragon.glb",  "blend_dragon_a", phi=80, radius="82%", sweep=300),
    T("tt_blend_dragon_b", "dragon.glb",  "blend_dragon_b", phi=80, radius="82%", sweep=300),
    T("tt_blend_dragon_n", "dragon.glb",  "nrm_dragon",     phi=80, radius="82%", sweep=300),
    T("tt_blend_leaf_a",   "bigleaf.glb", "blend_leaf_a",   phi=90, radius="88%"),
    T("tt_blend_leaf_b",   "bigleaf.glb", "blend_leaf_b",   phi=90, radius="88%"),
    T("tt_blend_leaf_c",   "bigleaf.glb", "blend_leaf_c",   phi=90, radius="88%"),
    T("tt_blend_leaf_d",   "bigleaf.glb", "blend_leaf_d",   phi=90, radius="88%"),
    T("tt_blend_leaf_n",   "bigleaf.glb", "nrm_bigleaf",    phi=90, radius="88%"),
    # 3.2 PBR -- same shape, three generated materials, light on the move
    L("tt_pbr_teal",  "cabbage_pbr.glb", "pbr_cab_teal",  "pbr_cab_teal_orm"),
    L("tt_pbr_gold",  "cabbage_pbr.glb", "pbr_cab_gold",  "pbr_cab_gold_orm"),
    L("tt_pbr_green", "cabbage_pbr.glb", "pbr_cab_green", "pbr_cab_green_orm"),
    L("tt_pbr_teal_flat", "cabbage_pbr.glb", "pbr_cab_teal", "pbr_cab_flat_orm"),
    # 3.3 zero-shot transfer onto an unseen tortoise
    T("tt_tr_tortoise_a", "tortoise.glb", "tr_tortoise_a", phi=72, radius="78%", sweep=35),
    T("tt_tr_tortoise_b", "tortoise.glb", "tr_tortoise_b", phi=72, radius="78%", sweep=35),
    T("tt_tr_tortoise_n", "tortoise.glb", "nrm_tortoise",  phi=72, radius="78%", sweep=35),
    # 3.4 automatic -- twelve results on one geometry, then the baselines
    dict(name="tt_auto_grid", glb="gourd_grid.glb", tex=None, mode="turn",
         phi=82, radius="76%", sweep=40),
]
for m in ("ours", "hunyuan", "trellis2", "mvadapter", "texgen", "paint3d"):
    SPECS.append(T(f"tt_auto_koi_{m}", "koi.glb", f"koi_{m}", phi=76, radius="88%", sweep=40))

PAGE = """<!doctype html><meta charset=utf-8>
<style>html,body{margin:0;background:#0f1510}
model-viewer{width:%dpx;height:%dpx;background:#0f1510;--poster-color:transparent}</style>
<script type="module" src="vendor/model-viewer.min.js"></script>
<model-viewer id="mv" camera-controls disable-zoom interaction-prompt="none"
  shadow-intensity="0" exposure="1.12"></model-viewer>
<script>
const mv = document.getElementById('mv');
const wait = () => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)));
window.setup = async (s) => {
  // Consecutive clips often share a mesh. Re-assigning the same src never
  // re-fires 'load', so waiting on it unconditionally hangs the run.
  const next = 'assets/models/' + s.glb;
  if (!mv.src || !mv.src.endsWith(next)) {
    mv.src = next;
    await new Promise(r => mv.addEventListener('load', r, {once:true}));
  }
  const mat = mv.model.materials[0];
  if (s.tex) mat.pbrMetallicRoughness.baseColorTexture
                .setTexture(await mv.createTexture('assets/tex/' + s.tex + '.webp'));
  if (s.orm) mat.pbrMetallicRoughness.metallicRoughnessTexture
                .setTexture(await mv.createTexture('assets/tex/' + s.orm + '.webp'));
  await wait(); await wait();
};
window.frame = async (s, t) => {
  const a = t * 360;
  if (s.mode === 'light') {           // shape still, environment turning
    mv.orientation = '0deg 0deg ' + a + 'deg';
    mv.cameraOrbit = (20 + a) + 'deg ' + s.phi + 'deg ' + s.radius;
  } else {                            // camera around the shape
    mv.cameraOrbit = ((s.sweep || 0) + a) + 'deg ' + s.phi + 'deg ' + s.radius;
  }
  await wait();
  return mv.toDataURL('image/png');
};
</script>""" % (W, H)


async def render(specs):
    from playwright.async_api import async_playwright
    open(f"{V}/_render.html", "w").write(PAGE)
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome")
        pg = await b.new_page(viewport={"width": W + 40, "height": H + 40})
        pg.on("pageerror", lambda e: print("   PAGEERROR", str(e)[:160]))
        await pg.goto(f"http://localhost:{PORT}/_render.html", wait_until="load")
        await pg.wait_for_timeout(3000)
        for s in specs:
            d = f"{TMP}/{s['name']}"
            os.makedirs(d, exist_ok=True)
            await pg.evaluate("s => window.setup(s)", s)
            for i in range(FRAMES):
                url = await pg.evaluate("([s,t]) => window.frame(s,t)",
                                        [s, i / FRAMES])
                img = Image.open(io.BytesIO(base64.b64decode(url.split(",", 1)[1])))
                flat = Image.new("RGB", img.size, STAGE)
                flat.paste(img, (0, 0), img if img.mode == "RGBA" else None)
                flat.save(f"{d}/{i:03d}.png")
            encode(s["name"], d)
        await b.close()
    os.remove(f"{V}/_render.html")


def encode(name, d):
    mp4 = f"{OUT}/{name}.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS),
         "-i", f"{d}/%03d.png", "-c:v", "libx264", "-preset", "slow",
         "-crf", "30", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
         "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2", mp4], check=True)
    # a still for the poster, so nothing pops in before the clip decodes
    Image.open(f"{d}/000.png").save(f"{OUT}/{name}.jpg", quality=82)
    print(f"   {name}.mp4 {os.path.getsize(mp4)//1024} KB")


if __name__ == "__main__":
    want = sys.argv[1:]
    specs = [s for s in SPECS if not want or s["name"] in want]
    print(f"rendering {len(specs)} clips, {FRAMES} frames each")
    asyncio.run(render(specs))
