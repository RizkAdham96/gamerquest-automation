# GamerQuest Production Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the WordPress image-repair workflow, diagnose remaining GamerQuest production failures, and verify the social carousel automation runs at the intended schedule without breaking healthy automations.

**Architecture:** Fix the confirmed WordPress REST update failure at the request boundary, then audit current GitHub Actions runs and workflow definitions for both the editorial automation and social carousel repositories. Keep changes minimal, test-backed, and isolated to confirmed faults.

**Tech Stack:** Python 3.12, requests, pytest, GitHub Actions, WordPress REST API, Meta/Instagram social automation.

**Spec:** User request in chat on 2026-10-03.

## Global Constraints

- Do not weaken or remove healthy automations.
- Preserve production safeguards and test gates.
- Prefer the smallest fix that addresses a verified root cause.
- Verify live workflow behavior after each production change.
- Carousel publishing schedule must match the currently agreed twice-daily cadence and retain the corrected full-frame visual behavior.

## Review Focus

- WordPress update body must actually contain non-empty content when repairing inline images.
- Updating a post must preserve existing title/excerpt/content outside the intended image insertion.
- Repair workflow must fail visibly if WordPress rejects updates.
- Existing healthy editorial workflows must remain green after the repair change.
- Carousel workflow timing and publish path must be verified from current production configuration and recent runs.

---

### Task 1: Repair WordPress inline-image update

**Files:**
- Modify: `scripts/repair_missing_featured_images.py`
- Modify/Test: `test_repair_missing_featured_images.py`

**Interfaces:**
- Consumes: existing WordPress post payload returned by REST API.
- Produces: successful authenticated update of existing post content with the inline featured image preserved alongside title/excerpt.

- [ ] Write/adjust a regression test that reproduces WordPress receiving an empty update body.
- [ ] Run the focused test and confirm failure before implementation.
- [ ] Change only the request construction/method needed so WordPress receives populated post fields.
- [ ] Run the focused test suite and confirm all featured-image tests pass.
- [ ] Trigger/observe the production repair workflow and verify repaired posts no longer return `empty_content`.

### Task 2: Diagnose gamerquest-automation production workflows

**Files:**
- Inspect: `.github/workflows/*.yml`
- Inspect: recent Actions runs and logs

**Interfaces:**
- Consumes: current main branch and recent production workflow outcomes.
- Produces: a list of confirmed remaining failures only.

- [ ] Inspect recent workflow runs for failures/cancellations.
- [ ] Read logs for each confirmed failing production job.
- [ ] Compare failing workflow configuration with healthy patterns in the repository.
- [ ] Fix only confirmed faults and rerun/observe validation.

### Task 3: Verify and repair carousel production automation

**Files:**
- Inspect/modify as required in `RizkAdham96/gamerquest-social-agent`.

**Interfaces:**
- Consumes: current carousel generation/publishing workflow and schedule.
- Produces: twice-daily scheduled carousel publishing with the corrected full-frame image format and no Reel automation dependency.

- [ ] Inspect workflow schedule and current carousel-only configuration.
- [ ] Inspect recent carousel runs and logs for failures.
- [ ] Correct schedule or publish logic only where current production differs from the agreed configuration.
- [ ] Verify the workflow parses/tests successfully and recent/manual validation reaches the publish path.

### Task 4: Final verification

**Files:**
- No code changes unless verification reveals a confirmed regression.

**Interfaces:**
- Consumes: final production state.
- Produces: evidence-based completion report.

- [ ] Verify latest relevant GitHub Actions runs are green or identify any external dependency that remains outside repository control.
- [ ] Confirm the image-repair workflow no longer emits `empty_content`.
- [ ] Confirm carousel schedule in source and publishing workflow health.
- [ ] Confirm no unrelated healthy workflow was disabled or weakened.
