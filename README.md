# GLOSS project page

Project website for **GLOSS: Geometric Local Self-Similarity Learning for Faithful Reference-Guided Texture Fill**.

Live site: https://chenyuecai.github.io/gloss-page/

## Structure

- `index.html` — the page (hero, abstract, teaser, video, BibTeX).
- `style.css` — styling, adapted from the [UniMate](https://linzhanm.github.io/unimate/) / VideoMimic template.
- `assets/` — teaser image, demo video, and poster frame.

## Editing

- **Authors:** edit the `.authors` / `.affil-note` block near the top of `index.html`.
- **Links:** the arXiv and Code buttons are disabled placeholders — replace the `href` and drop
  `class="disabled"` once the links are live.
- **Video:** `assets/gloss-video.mp4` is a web-compressed (720p) version of the original. Replace it in place
  to update.

Local preview: `python3 -m http.server` then open http://localhost:8000.
