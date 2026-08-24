# GLOSS project page

Project website for **GLOSS: Geometric Local Self-Similarity Learning for Faithful
Reference-Guided Texture Fill** (SIGGRAPH Asia 2026, DOI 10.1145/3829340.3842197).

Live site: https://chenyuecai.github.io/gloss-page/ — served by GitHub Pages from
`main` at the repository root.

## Structure

- `index.html`, `style.css`, `app.js` — the page. One dark ground with a green/orange
  accent pair; green carries structure, orange is reserved for emphasis.
- `assets/video/` — turntables and capture clips, at full render resolution.
- `assets/img/` — figures, result plates and reference thumbnails.
- `assets/models/`, `assets/tex/` — GLBs and texture maps for the interactive viewers.
- `assets/paper/` — the paper PDF.
- `vendor/model-viewer.min.js` — vendored so the page has no CDN dependency.
- `figures-src/` — the Method figures as exported from the paper, before recolouring.

## Regenerating things

Figures come from the paper deck rather than from bitmaps, so the labels stay vector:

    retone_slides.py     recolour a slide onto the page palette, in the deck
    render_pptx.py       deck -> one PNG per slide (LibreOffice + pdftoppm)
    crop_web.py          crop to the drawn area, resize, write assets/img/

`recolor-figures.py` is the older bitmap path, kept for the two figures that never
had a deck source.

`build-assets.py` builds the web GLBs and texture maps. `build-artifact.py` bundles the
whole page into one self-contained HTML file for a Claude Artifact — that output is
generated and is not tracked.

Local preview: `python3 -m http.server` then open http://localhost:8000.
