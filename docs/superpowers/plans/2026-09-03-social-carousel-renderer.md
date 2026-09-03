# Social Carousel Renderer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render each fact-checked GamerQuest carousel into five 1080x1350 branded PNG slides at zero operating cost.

**Architecture:** Add a deterministic Pillow renderer under `social/` plus a small CLI entry point. The renderer consumes only ready/fact-checked JSON and uses programmatic typography and layout variants; the existing workflow will install Pillow, run renderer tests, render the generated carousel, and upload the images.

**Tech Stack:** Python 3.12, Pillow, unittest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-03-social-carousel-renderer.md`

## Global Constraints
- Zero operating cost.
- No paid image API.
- Do not modify SEO/news/deals behavior.
- Output size is exactly 1080x1350 PNG.
- Text is always rendered programmatically.
- Only `status=ready` and `fact_checked=true` input may render.

---

### Task 1: Renderer Core

**Files:**
- Create: `social/renderer.py`
- Create: `tests/social/test_renderer.py`

**Interfaces:**
- Consumes: carousel dictionary from `social-output.json`.
- Produces: `render_carousel(carousel, output_dir) -> list[Path]` and `render_slide(slide, index, total, output_path)`.

- [ ] Step 1: Write failing tests for five output files, exact dimensions, and safe ready/fact-check validation helper behavior.
- [ ] Step 2: Run renderer tests and verify RED because renderer module/functions do not exist.
- [ ] Step 3: Implement minimal deterministic Pillow renderer with dark background, accent shapes, text wrapping, slide number, brand footer, and three layout variants.
- [ ] Step 4: Run renderer tests and verify GREEN.
- [ ] Step 5: Commit renderer core.

### Task 2: CLI and Input Validation

**Files:**
- Create: `social/render.py`
- Modify: `tests/social/test_renderer.py`

**Interfaces:**
- Consumes: `social-output.json`.
- Produces: `social-rendered/slide-01.png` ... `slide-05.png` and `social-rendered/manifest.json`.

- [ ] Step 1: Add failing tests that non-ready/non-fact-checked payloads do not render and ready payloads produce manifest metadata.
- [ ] Step 2: Verify RED.
- [ ] Step 3: Implement `render_from_output(input_path, output_dir)` and CLI main.
- [ ] Step 4: Verify GREEN.
- [ ] Step 5: Commit CLI.

### Task 3: GitHub Actions Integration

**Files:**
- Modify: `.github/workflows/social-test.yml`

**Interfaces:**
- Consumes: existing social generation result.
- Produces: artifact containing JSON plus rendered PNGs when status is ready.

- [ ] Step 1: Add Pillow installation from requirements (or `pip install Pillow`) before renderer tests.
- [ ] Step 2: Run `python tests/social/test_renderer.py` in CI.
- [ ] Step 3: Run `python -m social.render` after `python -m social.run`; renderer should gracefully skip non-ready output.
- [ ] Step 4: Upload `social-output.json` and `social-rendered/` in the artifact.
- [ ] Step 5: Trigger manual workflow and verify all tests, real generation, fact-check, rendering, and artifact upload.
