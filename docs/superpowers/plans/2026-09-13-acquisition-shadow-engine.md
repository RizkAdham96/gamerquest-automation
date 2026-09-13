# Acquisition Shadow Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an isolated, zero-cost shadow acquisition engine that ranks traffic opportunities without modifying existing production publishing workflows.

**Architecture:** Add a new `acquisition/` package that reads current GamerQuest repository outputs, normalizes candidate opportunities, scores them deterministically, applies a historical duplicate guard, and writes a ranked shadow queue. A new independent GitHub Actions workflow runs tests and the shadow engine on a schedule and never publishes to WordPress or social channels.

**Tech Stack:** Python 3.12, stdlib JSON/pathlib/re/datetime, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-09-13-acquisition-shadow-engine-design.md`

## Global Constraints
- €0 hard constraint; no paid API or new paid service.
- Do not modify existing News, Deals, Reviews, Social, or WordPress publishing workflow files in phase 1.
- No WordPress or social publishing from this subsystem.
- Missing optional input files must degrade safely to empty data.
- All generated state/output belongs under `acquisition/`.

---

### Task 1: Acquisition scoring core

**Files:**
- Create: `acquisition/__init__.py`
- Create: `acquisition/engine.py`
- Test: `acquisition/test_engine.py`

**Interfaces:**
- Produces: `collect_candidates(root: Path) -> list[dict]`
- Produces: `score_candidate(candidate: dict, covered_articles: list[dict]) -> dict`
- Produces: `build_shadow_queue(root: Path) -> dict`
- Produces: `write_shadow_queue(root: Path, output_path: Path | None = None) -> dict`

- [ ] **Step 1: Write failing tests**

Add tests for:
```python
def test_specific_long_tail_beats_broad_head_term(): ...
def test_historical_duplicate_is_blocked(): ...
def test_missing_optional_inputs_are_safe(): ...
def test_deal_free_window_gets_freshness_credit(): ...
def test_queue_is_sorted_by_score_descending(): ...
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest acquisition/test_engine.py -v`
Expected: FAIL because `acquisition.engine` does not exist.

- [ ] **Step 3: Implement minimal deterministic engine**

Implement a normalized candidate schema and pure scoring functions. Use only evidence in repository files. Add phrase detectors for specific search intent (`date de sortie`, `plateforme`, `comment`, `erreur`, `problème`, `patch`, `performance`, `crossplay`, `gratuit`, `promo`) and broad-topic penalties. Reuse normalized token overlap ideas from the existing News duplicate guard without importing `automation.py`, so missing environment secrets cannot break this subsystem.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest acquisition/test_engine.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

Commit message: `feat: add isolated acquisition scoring engine`

### Task 2: Shadow queue CLI and current-data generation

**Files:**
- Create: `acquisition/run_shadow.py`
- Create/Update generated: `acquisition/shadow_queue.json`
- Test: `acquisition/test_shadow_cli.py`

**Interfaces:**
- Consumes: `write_shadow_queue()` from Task 1.
- Produces: CLI exit code 0 on valid/missing optional inputs; prints ranked summary.

- [ ] **Step 1: Write failing CLI test**

Use a temp repository fixture and assert the CLI writes a queue containing `generated_at`, `count`, and sorted `opportunities`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest acquisition/test_shadow_cli.py -v`
Expected: FAIL because `run_shadow.py` does not exist.

- [ ] **Step 3: Implement CLI**

`run_shadow.py` calls the engine from repository root, writes `acquisition/shadow_queue.json`, and prints top `PRIORITIZE`/`WATCH` opportunities. It performs no network requests.

- [ ] **Step 4: Generate a real queue from current repository data**

Run: `python -m acquisition.run_shadow`
Expected: `acquisition/shadow_queue.json` created with at least one candidate when current source files contain data.

- [ ] **Step 5: Run tests**

Run: `python -m pytest acquisition/test_engine.py acquisition/test_shadow_cli.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

Commit message: `feat: generate acquisition shadow queue`

### Task 3: Independent scheduled workflow

**Files:**
- Create: `.github/workflows/acquisition-shadow.yml`

**Interfaces:**
- Consumes: acquisition tests and CLI.
- Produces: scheduled/manual workflow that only commits `acquisition/shadow_queue.json`.

- [ ] **Step 1: Create workflow**

Workflow requirements:
```yaml
name: GamerQuest Acquisition Shadow
on:
  workflow_dispatch:
  schedule:
    - cron: "17 */6 * * *"
permissions:
  contents: write
```

Steps: checkout, Python 3.12, install `requirements.txt`, run acquisition tests, run `python -m acquisition.run_shadow`, commit only `acquisition/shadow_queue.json` when changed.

- [ ] **Step 2: Verify existing production workflows are untouched**

Compare the feature branch to `main` and confirm no existing `.github/workflows/*.yml` file was modified; only `acquisition-shadow.yml` is added.

- [ ] **Step 3: Run full relevant regression suite**

Run acquisition tests plus existing News quality tests where environment-safe. The acquisition package must import without `GROQ_API_KEY` or `TAVILY_API_KEY`.

- [ ] **Step 4: Commit**

Commit message: `ci: add isolated acquisition shadow workflow`

### Task 4: Verification and handoff

**Files:**
- No production file changes expected.

- [ ] **Step 1: Verify branch diff**
Confirm only new acquisition files, docs, and one new workflow exist.

- [ ] **Step 2: Verify workflow run**
Push branch changes and inspect the workflow run. If schedule-only does not trigger on a non-default branch, use `workflow_dispatch` or temporarily rely on CI tests in branch; do not modify existing production workflows.

- [ ] **Step 3: Create PR**
Open a PR to `main` summarizing isolation guarantees, tests, generated sample queue, and the fact that no publishing path is connected.

- [ ] **Step 4: Do not merge automatically**
Leave the PR ready for review. Activation on `main` is a separate merge decision because the user explicitly asked that the old automation not be endangered.