# Balanced Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce GamerQuest scheduled automation load and duplicate work while preserving content freshness and production safety.

**Architecture:** Production workflows run only on schedules/manual dispatches and perform lightweight preflight plus production work. Regression suites move to change-driven CI. Social scheduling is consolidated into one workflow, and Deals performs a single collection/build/publish pass.

**Tech Stack:** GitHub Actions YAML, Python 3.12, unittest/pytest.

**Spec:** Conversation-approved Option B on 2026-09-28.

## Global Constraints

- News: 4 scheduled runs/day.
- SEO: 1 scheduled run/day.
- Deals: 6 scheduled runs/day.
- Reviews: 1 scheduled run/day.
- Health: 4 scheduled runs/day.
- Acquisition Shadow: 1 scheduled run/day.
- Social: Tuesday, Friday, Sunday directly from the primary workflow.
- Ordinary code pushes must never invoke production publishing workflows.
- Regression tests run in CI, not on every scheduled production execution.
- Preserve manual workflow dispatch for operational recovery/diagnostics.
- Keep global repository writer serialization for state-writing production jobs.

## Review Focus

- A code push must not publish WordPress or Meta content.
- Sunday social publishing must run directly without a dispatcher workflow.
- Recovery cadence must match all three social days.
- Health thresholds must remain compatible with daily Reviews while still detecting stale News.
- Deals must not perform repeated source scans inside one production run.

---

### Task 1: Workflow policy guard

**Files:**
- Create: `tests/test_workflow_policy.py`
- Create: `.github/workflows/automation-policy-ci.yml`

**Interfaces:**
- Consumes: workflow files under `.github/workflows/`.
- Produces: executable policy checks for Option B.

- [ ] Write policy tests for schedules, no production push triggers, CI separation, social consolidation, and Deals single-pass behavior.
- [ ] Run in GitHub Actions and verify RED against current workflows.

### Task 2: Production schedule and trigger cleanup

**Files:**
- Modify: `.github/workflows/gamerquest.yml`
- Modify: `.github/workflows/run-trending-seo-pipeline.yml`
- Modify: `.github/workflows/test-deals.yml`
- Modify: `.github/workflows/reviews.yml`
- Modify: `.github/workflows/content-health.yml`
- Modify: `.github/workflows/acquisition-shadow.yml`
- Modify: `.github/workflows/social-test.yml`
- Modify: `.github/workflows/social-publish-recovery.yml`
- Delete: `.github/workflows/social-sunday.yml`
- Delete: `.github/workflows/social-publish-now-once.yml`

**Interfaces:**
- Consumes: Option B policy from Task 1.
- Produces: lower-frequency, production-only scheduled workflows.

- [ ] Apply exact Option B crons and remove push triggers from production workflows.
- [ ] Remove scheduled regression-test steps and unnecessary pip upgrade work.
- [ ] Collapse Deals production to build-feed once then publish once.
- [ ] Add Sunday directly to primary Social and recovery schedules.
- [ ] Split health freshness limits: News <= 8h, Reviews <= 30h.

### Task 3: Change-driven CI consolidation

**Files:**
- Modify: `.github/workflows/news-quality-ci.yml`
- Modify: `.github/workflows/seo-quality-ci.yml`
- Create: `.github/workflows/deals-quality-ci.yml`
- Create: `.github/workflows/reviews-quality-ci.yml`
- Create: `.github/workflows/social-quality-ci.yml`
- Create: `.github/workflows/acquisition-quality-ci.yml`
- Delete: `.github/workflows/test-trending-seo.yml`
- Delete: `.github/workflows/social-image-selection-ci.yml`

**Interfaces:**
- Consumes: regression suites removed from production in Task 2.
- Produces: push/PR quality gates without production side effects.

- [ ] Preserve all meaningful existing regression coverage in dedicated CI.
- [ ] Remove duplicate SEO and Social CI coverage.
- [ ] Run policy CI and all affected quality suites GREEN.

### Task 4: Final verification and merge

**Files:**
- Review all changed workflow files and PR diff.

**Interfaces:**
- Consumes: Tasks 1-3.
- Produces: verified main-branch automation architecture.

- [ ] Verify changed YAML parses through GitHub Actions workflow runs.
- [ ] Confirm policy CI GREEN and affected quality CI jobs GREEN.
- [ ] Review PR diff for accidental production side effects.
- [ ] Merge to `main` only after verification.
