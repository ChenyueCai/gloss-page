#!/usr/bin/env python3
"""Bundle the GLOSS page into one self-contained HTML file for an Artifact.

The sandbox blocks every external request and caps the page at 16 MB, so this:
  * discovers every asset the page references (no hand-maintained list),
  * rebuilds each at a size that fits the budget - GLBs without Draco, whose
    decoder is fetched from a CDN the sandbox blocks,
  * inlines the stylesheet, model-viewer and the page script,
  * ships binaries as base64 the page turns into blob: URLs at start-up
    (blob: for <img>/<video>, which img-src and media-src admit; model-viewer
    fetches its .glb, and connect-src 'self' matches neither blob: nor data:,
    so those requests are answered from memory by a patched fetch instead).

Usage:  python3 build-artifact.py
"""
import base64, json, os, re, shutil, subprocess, sys, tempfile

SRC  = os.path.dirname(os.path.abspath(__file__))
OUT  = os.path.join(SRC, "gloss-artifact.html")
WORK = os.path.join(tempfile.gettempdir(), "gloss-artifact-build")
GLTF = "@gltf-transform/cli@4.1.1"        # newer CLIs require node >= 22

IMG_MAX_W, IMG_Q          = 560, 62
GLB_TEX                   = 256
VIDEO_W, VIDEO_CRF        = 660, 36   # 90 clips: the per-clip budget stays tight
HERO_W, HERO_CRF          = 1000, 31      # the hero loop earns a little more
PDF_DPI                   = 90

MIME = {".glb": "model/gltf-binary", ".webp": "image/webp", ".pdf": "application/pdf",
        ".mp4": "video/mp4", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".svg": "image/svg+xml"}


def sh(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


WIDE_MAX_W, WIDE_Q = 1600, 78  # full-width figures span the whole column,
WIDE = ("teaser_flow", "fig_")   # any label-dense figure keeps its resolution  # so 560px would visibly blur their labels
TEX_MAX_W, TEX_Q = 768, 72     # UV maps wrap a whole mesh, so they keep more

def shrink_image(src, dst, rel=""):
    """Flat page imagery can go small; a UV texture is stretched over a whole
    surface, so it keeps more resolution or the models look muddy."""
    from PIL import Image
    Image.MAX_IMAGE_PIXELS = None
    tex = "/tex/" in rel
    wide = any(k in rel for k in WIDE)
    maxw, q = (WIDE_MAX_W, WIDE_Q) if wide else \
              (TEX_MAX_W, TEX_Q) if tex else (IMG_MAX_W, IMG_Q)
    im = Image.open(src)
    # figures composited onto the page ground carry alpha; converting to RGB
    # would silently restore the white background that was removed from them
    keep_alpha = im.mode in ("RGBA", "LA") or "transparency" in im.info
    im = im.convert("RGBA" if keep_alpha else "RGB")
    if im.size[0] > maxw:
        im = im.resize((maxw, round(maxw * im.size[1] / im.size[0])), Image.LANCZOS)
    im.save(dst, "WEBP", quality=q, method=6)


# A comparison filmstrip is N square panels in one frame, so the page only ever
# shows width/N of it. Scaling it like an ordinary clip would leave each method
# 100 px wide; it gets a budget per panel instead.
STRIP_PANELS = {"app_auto_cmp": 7, "app_auto_ft": 5}
# the comparison row shows all seven panels at once, so each one lands
# about 160 px wide on a full-width page; 210 covers that with headroom
STRIP_PANEL_W, STRIP_CRF = 210, 31
# Section 4 alone carries 44 turnarounds. They are small, dark and looping,
# which hides a higher CRF well, and without this the bundle clears 16 MB.
APP_CRF = 37


def shrink_video(src, dst, hero=False, rel=""):
    w, crf = (HERO_W, HERO_CRF) if hero else (VIDEO_W, VIDEO_CRF)
    for key, n in STRIP_PANELS.items():
        if key in rel:
            return _enc(src, dst, STRIP_PANEL_W * n, STRIP_CRF)
    # the completion gallery renders in ~190 px cells, so encoding those forty
    # clips at the full video budget spent bytes no viewer could ever see
    if "/app_auto_show_" in rel:
        return _enc(src, dst, 300, APP_CRF)
    if "/app_" in rel:
        crf = APP_CRF
    return _enc(src, dst, w, crf)


def _enc(src, dst, w, crf):
    # a width target, not a resize: several sources are already narrower than
    # the budget and enlarging them spends bytes on detail that is not there
    sh(["ffmpeg", "-v", "error", "-i", src, "-vf", f"scale='min({w},iw)':-2",
        "-c:v", "libx264", "-crf", str(crf), "-preset", "slow", "-an",
        "-movflags", "+faststart", "-pix_fmt", "yuv420p", dst, "-y"])


def shrink_pdf(src, dst):
    sh(["gs", "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.7", "-dPDFSETTINGS=/ebook",
        "-dDownsampleColorImages=true", f"-dColorImageResolution={PDF_DPI}",
        "-dDownsampleGrayImages=true", f"-dGrayImageResolution={PDF_DPI}",
        "-dNOPAUSE", "-dQUIET", "-dBATCH", f"-sOutputFile={dst}", src])
    if not os.path.exists(dst):
        shutil.copy(src, dst)


def strip_draco(src, dst):
    """model-viewer fetches the Draco decoder from a CDN the sandbox blocks, so
    the sandbox copy carries plain geometry. That makes geometry the dominant
    cost, so the decorative multi-gourd grid is decimated here; the hero meshes
    keep every triangle, since the page quotes their counts."""
    decimate = "grid" in os.path.basename(src)
    cmd = ["npx", "--yes", GLTF, "optimize", src, dst,
           "--texture-compress", "webp", "--texture-size", str(GLB_TEX),
           "--compress", "false"]
    cmd += ["--simplify-error", "0.002"] if decimate else ["--simplify", "false"]
    r = sh(cmd)
    if not os.path.exists(dst):
        print("  ! gltf-transform failed, copying as-is:", r.stderr.strip()[:100], file=sys.stderr)
        shutil.copy(src, dst)


def build():
    html = open(os.path.join(SRC, "index.html")).read()
    appsrc = open(os.path.join(SRC, "app.js")).read()
    # app.js loads shapes and texture sets at runtime through __ga(), so its
    # paths must be bundled too - scanning the markup alone misses roughly half.
    paths = sorted(set(re.findall(r'assets/[A-Za-z0-9_./-]+', html + "\n" + appsrc)))
    os.makedirs(WORK, exist_ok=True)

    blobs, raw_total = {}, 0
    for rel in paths:
        src = os.path.join(SRC, rel)
        if not os.path.isfile(src):
            print("  ! missing, skipped:", rel, file=sys.stderr)
            continue
        ext = os.path.splitext(rel)[1].lower()
        out_ext = ".webp" if ext in (".jpg", ".jpeg", ".png", ".webp") else ext
        dst = os.path.join(WORK, os.path.splitext(rel.replace("/", "_"))[0] + out_ext)

        # Keyed on filename alone, this cache never noticed a source change, so
        # a rebuilt figure kept shipping as whatever was encoded first and two
        # publishes went out carrying stale artwork. Re-encode when the source
        # is newer; everything untouched still comes from cache.
        if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
            if ext in (".jpg", ".jpeg", ".png", ".webp"):  shrink_image(src, dst, rel)
            elif ext == ".mp4":                   shrink_video(src, dst, hero="hero" in rel, rel=rel)
            elif ext == ".glb":                   strip_draco(src, dst)
            elif ext == ".pdf":                   shrink_pdf(src, dst)
            else:                                 shutil.copy(src, dst)

        data = open(dst, "rb").read()
        raw_total += len(data)
        blobs[rel] = {"m": MIME.get(out_ext, "application/octet-stream"),
                      "d": base64.b64encode(data).decode("ascii")}
        print(f"  {rel:46s} {os.path.getsize(src)/1e6:7.2f} -> {len(data)/1e6:6.2f} MB", file=sys.stderr)

    css = open(os.path.join(SRC, "style.css")).read()
    app = open(os.path.join(SRC, "app.js")).read()
    # model-viewer is ~1 MB of base64 once inlined; ship it only if the page
    # still has a viewer to run it. The turntable clips need no WebGL.
    needs_mv = "<model-viewer" in html
    mv  = open(os.path.join(SRC, "vendor/model-viewer.min.js")).read() if needs_mv else ""

    body = html
    body = re.sub(r"<!DOCTYPE html>|</?html[^>]*>|</?head>|</?body>", "", body)
    body = re.sub(r'<meta charset[^>]*>|<meta name="viewport"[^>]*>', "", body)
    body = re.sub(r'<link rel="icon"[^>]*>', "", body)
    body = re.sub(r'<link rel="stylesheet" href="style\.css">', "", body)
    body = re.sub(r'<script type="module" src="vendor/model-viewer\.min\.js"></script>', "", body)
    body = re.sub(r'<script src="app\.js"></script>', "", body)
    t = re.search(r"<title>.*?</title>", body, re.S)
    f = re.search(r'<link rel="stylesheet" href="https://fonts\.googleapis[^>]*>', body)
    fonts = f.group(0) if f else ""
    if t: body = body.replace(t.group(0), "")
    body = body.replace(fonts, "")
    body = re.sub(r'<meta (name|property)="[^"]+" content="[^"]*">', "", body)
    body = body.strip()

    # <img>/<video> src is fetched while parsing, before the loader can rewrite
    # it, which produces a burst of 404s. Park the path in data-src instead.
    body = re.sub(r'(<(?:img|video|model-viewer)\b[^>]*?)\ssrc="(assets/[^"]+)"',
                  r'\1 data-src="\2"', body)
    body = re.sub(r'(<[^>]*?)\sposter="(assets/[^"]+)"', r'\1 data-poster="\2"', body)

    # the published page inherits a <head> we do not control, so instead of
    # trusting it to declare UTF-8, non-ASCII becomes entities / \u escapes
    body = "".join(c if ord(c) < 128 else "&#%d;" % ord(c) for c in body)
    app  = "".join(c if ord(c) < 128 else "\\u%04x" % ord(c) for c in app)

    loader = """
(function () {
  /* Every blob: URL the page mints, kept so it can be read back without a
     network request. Installed before model-viewer parses anything, because
     GLTFLoader mints its own for each texture embedded in a .glb. */
  var BLOBS = Object.create(null);
  var realCreate = URL.createObjectURL.bind(URL);
  var realRevoke = URL.revokeObjectURL.bind(URL);
  URL.createObjectURL = function (obj) {
    var u = realCreate(obj);
    if (obj instanceof Blob) BLOBS[u] = obj;
    return u;
  };
  URL.revokeObjectURL = function (u) { delete BLOBS[u]; return realRevoke(u); };

  /* Answer requests for those blobs locally instead of over the network.

     <img> and <video> read a blob: URL straight off, but model-viewer *fetches*
     the .glb and three's ImageBitmapLoader fetches each embedded texture, and
     fetch is governed by connect-src -- 'self' in the artifact sandbox. A blob:
     URL is same-origin and still does not match 'self', so those requests are
     refused and the viewers render empty. Serving them from the blob we already
     hold leaves no request for the policy to reject. */
  var realFetch = window.fetch && window.fetch.bind(window);
  window.fetch = function (input, init) {
    var u = typeof input === 'string' ? input
          : (input && input.url) ? input.url : String(input);
    if (BLOBS[u]) return Promise.resolve(new Response(BLOBS[u], { status: 200 }));
    return realFetch ? realFetch(input, init)
                     : Promise.reject(new Error('fetch unavailable'));
  };

  var A = window.__GLOSS_ASSETS__, URLS = {};
  function toURL(e) {
    var bin = atob(e.d), n = bin.length, b = new Uint8Array(n);
    for (var i = 0; i < n; i++) b[i] = bin.charCodeAt(i);
    return URL.createObjectURL(new Blob([b], { type: e.m }));
  }
  for (var k in A) URLS[k] = toURL(A[k]);
  delete window.__GLOSS_ASSETS__;
  // Rewrite every attribute that can hold an asset path, INCLUDING the ones the
  // controls read later (data-vid / data-alb / data-orm on the buttons) - miss
  // one and that control silently does nothing once there is no server.
  ['src','href','poster','data-src','data-poster','data-tex','data-vid',
   'data-alb','data-orm','data-glb','data-normal','data-map'].forEach(function (a) {
    document.querySelectorAll('[' + a + ']').forEach(function (el) {
      var v = el.getAttribute(a);
      if (URLS[v]) el.setAttribute(a, URLS[v]);
    });
  });
  // media elements were parked so nothing was fetched during parsing; now that
  // the values are blobs, hand them back (buttons keep theirs as data only)
  document.querySelectorAll('video[data-src],img[data-src]').forEach(function (el) {
    el.setAttribute('src', el.getAttribute('data-src'));
  });
  document.querySelectorAll('video[data-poster],img[data-poster]').forEach(function (el) {
    el.setAttribute('poster', el.getAttribute('data-poster'));
  });
  // app.js routes every asset path through __ga(); defining it here (before
  // app.js runs, which keeps its own `|| identity` fallback) is what makes the
  // runtime-loaded GLBs and textures resolve to blobs instead of network paths.
  window.__ga = function (p) { return URLS[p] || p; };
  window.__GLOSS_URL__ = window.__ga;
})();
"""

    paper_js = """
(function () {
  var btn = document.querySelector('.links a.primary');
  if (!btn) return;
  btn.addEventListener('click', function (e) {
    var href = btn.getAttribute('href');
    if (!href || href.indexOf('blob:') !== 0) return;
    e.preventDefault();
    var w = null;
    // no 'noopener': with it window.open returns null by spec and we could not
    // tell a real window from a blocked one.
    try { w = window.open(href, '_blank'); } catch (_) {}
    if (w) { try { w.opener = null; } catch (_) {} return; }
    if (document.getElementById('pdfOverlay')) return;
    var ov = document.createElement('div');
    ov.id = 'pdfOverlay';
    ov.setAttribute('role', 'dialog');
    ov.setAttribute('aria-label', 'Paper');
    ov.style.cssText = 'position:fixed;inset:0;z-index:200;background:rgba(6,9,7,.92);' +
      'display:flex;flex-direction:column;padding:22px;gap:12px';
    var bar = document.createElement('div');
    bar.style.cssText = 'display:flex;justify-content:space-between;align-items:center;' +
      'font-family:var(--font-mono);font-size:12px;letter-spacing:.08em;color:var(--ink-2)';
    var lab = document.createElement('span');
    lab.textContent = 'GLOSS \\u00b7 SIGGRAPH Asia 2026';
    var close = document.createElement('button');
    close.textContent = 'Close';
    close.style.cssText = 'font:inherit;letter-spacing:.06em;padding:8px 18px;cursor:pointer;' +
      'border:1px solid var(--line);border-radius:var(--radius);background:var(--panel);color:var(--ink)';
    bar.appendChild(lab); bar.appendChild(close);
    var fr = document.createElement('iframe');
    fr.src = href;
    fr.style.cssText = 'flex:1;width:100%;border:1px solid var(--line);border-radius:var(--radius);background:#fff';
    ov.appendChild(bar); ov.appendChild(fr);
    var kill = function () { ov.remove(); document.removeEventListener('keydown', key); };
    var key = function (ev) { if (ev.key === 'Escape') kill(); };
    close.addEventListener('click', kill);
    ov.addEventListener('click', function (ev) { if (ev.target === ov) kill(); });
    document.addEventListener('keydown', key);
    document.body.appendChild(ov);
    close.focus();
  });
})();
"""

    out = "\n".join([
        "<title>GLOSS Texture Fill</title>",
        fonts,
        "<style>\n" + css + "\n</style>",
        body,
        "<script>window.__GLOSS_ASSETS__=" + json.dumps(blobs) + ";</script>",
        "<script>" + loader + "</script>",
        ('<script type="module">\n' + mv + "\n</script>") if needs_mv else "",
        "<script>\n" + app + "\n</script>",
        "<script>" + paper_js + "</script>",
    ])
    open(OUT, "w").write(out)
    mb = os.path.getsize(OUT) / 1e6
    print("\n%d assets, %.2f MB raw" % (len(blobs), raw_total / 1e6), file=sys.stderr)
    print("wrote %s - %.2f MB %s" % (OUT, mb, "(OVER 16 MB CAP)" if mb > 16 else "(within cap)"),
          file=sys.stderr)


if __name__ == "__main__":
    build()
