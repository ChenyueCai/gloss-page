#!/usr/bin/env python3
"""Render a .pptx to one PNG per slide so slides can actually be looked at.

Without this the deck is written blind - python-pptx reports no layout, so
overflow, collisions and low contrast only surface when a human opens the file.

Usage:  python3 render_pptx.py deck.pptx [outdir] [--dpi 110]
"""
import os, subprocess, sys, glob, shutil

SOFFICE = "/Applications/LibreOffice.app/Contents/MacOS/soffice"

def render(pptx, outdir="slides_png", dpi=110):
    pptx = os.path.abspath(pptx)
    outdir = os.path.abspath(outdir)
    os.makedirs(outdir, exist_ok=True)
    if not os.path.exists(SOFFICE):
        sys.exit("LibreOffice not found at " + SOFFICE)

    # pptx -> pdf, then pdf -> png per page (direct pptx->png only does slide 1)
    r = subprocess.run([SOFFICE, "--headless", "--convert-to", "pdf",
                        "--outdir", outdir, pptx], capture_output=True, text=True)
    pdf = os.path.join(outdir, os.path.splitext(os.path.basename(pptx))[0] + ".pdf")
    if not os.path.exists(pdf):
        sys.exit("conversion failed: " + (r.stderr or r.stdout)[:400])

    for old in glob.glob(os.path.join(outdir, "slide-*.png")):
        os.remove(old)
    subprocess.run(["pdftoppm", "-png", "-r", str(dpi), pdf,
                    os.path.join(outdir, "slide")], check=True)
    pngs = sorted(glob.glob(os.path.join(outdir, "slide-*.png")))
    for p in pngs:
        print(f"  {os.path.basename(p)}")
    print(f"{len(pngs)} slide(s) -> {outdir}")
    return pngs

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dpi = 110
    if "--dpi" in sys.argv:
        dpi = int(sys.argv[sys.argv.index("--dpi") + 1])
    render(args[0], args[1] if len(args) > 1 else "slides_png", dpi)
