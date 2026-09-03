# GamerQuest Social Carousel Renderer Spec

## Goal
Turn a fact-checked `social-output.json` carousel into five 1080x1350 branded PNG slides at zero operating cost.

## Constraints
- Do not modify SEO/news/deals behavior.
- Do not add paid image APIs.
- Use Pillow, already present in `requirements.txt`.
- Render all text programmatically so AI never draws text.
- Consume only `status=ready` and `fact_checked=true` social output.
- Preserve the caption/CTA/hashtags in JSON; images contain slide copy only.
- Output five PNGs under `social-rendered/`.

## Visual Direction
Dark gaming editorial aesthetic with a warm yellow/orange GamerQuest accent, bold white typography, strong hierarchy, generous margins, and varied slide compositions. Version 1 uses deterministic graphic backgrounds and available slide text; no external image generation is required.

## Architecture
`social/renderer.py` reads the ready carousel package and renders each slide with Pillow. It uses deterministic layout variants based on slide index, text wrapping, safe margins, accent shapes, slide number/progress, and a small GamerQuest brand footer. `social/render.py` is the CLI entry point that reads `social-output.json`, validates eligibility, creates `social-rendered/`, and writes `slide-01.png` through `slide-05.png` plus a small render manifest.

## CI
The existing manual `GamerQuest Social Test` workflow installs Pillow, runs renderer tests, runs the real social generation, renders the generated carousel only when it is ready, and uploads both JSON and rendered PNGs as artifacts.

## Acceptance Criteria
- Exactly five 1080x1350 PNGs are produced for a valid five-slide carousel.
- Renderer refuses non-ready or non-fact-checked input.
- Long title/body text wraps and stays inside safe bounds.
- No network dependency is required for rendering.
- Existing social AI tests remain green.
