# Tests & Avis Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a €0 pipeline that creates and refreshes GamerQuest Tests & Avis posts from Steam player-review data.

**Architecture:** A focused `reviews/` package discovers games from current GamerQuest feeds, enriches them through free Steam endpoints, builds transparent French player-review pages, and publishes/updates them through the standard WordPress REST API. A dedicated GitHub Actions workflow runs tests and the pipeline daily.

**Tech Stack:** Python 3.12, requests, pytest, GitHub Actions, WordPress REST API, Steam public store/review endpoints.

**Spec:** `docs/superpowers/specs/2026-09-09-tests-avis-automation-design.md`

## Global Constraints
- Total operating cost: €0.
- Do not claim automated scores are hands-on editorial reviews.
- Publish to existing WordPress category slug `tests`.
- Image failure must not block article publication.
- Do not create duplicate posts for the same Steam app.

---

### Task 1: Discovery and score model
**Files:** Create `reviews/discovery.py`, `reviews/pipeline.py`, `reviews/test_reviews.py`.
- [ ] Add failing tests for feed discovery, verdict thresholds, and transparent score generation.
- [ ] Implement feed candidate discovery with deduplication and a run limit.
- [ ] Implement 0–5 score and French review HTML generation.
- [ ] Run `python -m pytest reviews/test_reviews.py -q`.

### Task 2: Steam enrichment
**Files:** Create `reviews/steam.py`; extend `reviews/test_reviews.py`.
- [ ] Add a failing test proving exact Steam title matches beat loose matches.
- [ ] Implement free Steam search, app-details and aggregate-review retrieval.
- [ ] Run `python -m pytest reviews/test_reviews.py -q`.

### Task 3: WordPress publishing
**Files:** Create `reviews/wordpress.py`; extend `reviews/test_reviews.py`.
- [ ] Add a failing test for category assignment, deterministic slug and featured media payload.
- [ ] Implement `tests` category lookup, featured-image upload, create/update behavior.
- [ ] Run `python -m pytest reviews/test_reviews.py -q`.

### Task 4: Runner and automation
**Files:** Create `reviews/run.py`, `reviews/__init__.py`, `.github/workflows/reviews.yml`.
- [ ] Implement per-candidate error isolation and all-failed visibility.
- [ ] Add GitHub Actions test + publish workflow using existing WordPress secrets.
- [ ] Run `python -m py_compile reviews/*.py` and `python -m pytest reviews/test_reviews.py -q`.
- [ ] Verify a fresh GitHub Actions run and inspect WordPress publication result before claiming completion.
