# GamerQuest Evergreen SEO Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the existing `trending_seo` automation into a fully automatic evergreen French gaming SEO engine that targets durable search intent, prevents cannibalization, verifies content quality, creates a relevant SEO featured image, and publishes to WordPress only after every gate passes.

**Architecture:** Keep the current subsystem boundaries. `scorer.py` owns opportunity scoring, `seo_engine.py` owns deterministic evergreen/cannibalization rules, `researcher.py` owns evidence collection, and `pipeline.py` owns generation, image handling, WordPress publishing, and persistent publish history. Do not create a second SEO stack and do not modify the News, Social, or Deals implementations.

**Tech Stack:** Python 3.12, unittest, Groq `openai/gpt-oss-120b`, requests, BeautifulSoup, GitHub Actions, WordPress REST API.

**Spec:** `docs/superpowers/specs/2026-09-07-evergreen-seo-engine-design.md`

## Global Constraints

- Main News automation remains unchanged and continues its current schedule.
- Automatic WordPress publishing remains enabled for the SEO pipeline after validation gates pass.
- Existing News image generation remains untouched.
- Existing social automation and social image generation remain untouched.
- Deals automation remains untouched.
- The SEO pipeline may reuse existing infrastructure, but it must not modify the News feed logic or social/deals workflows.
- Maximum SEO output remains conservative: one SEO article per SEO run unless explicitly changed later.
- Groq remains the only AI provider for this SEO subsystem; no paid fallback is added.

---

## File Structure

- Modify `trending_seo/scorer.py`: evergreen-first scoring criteria and AI scoring prompt.
- Modify `trending_seo/test_scorer.py`: deterministic score and prompt regression coverage.
- Modify `trending_seo/seo_engine.py`: normalized search-intent keys, evergreen eligibility rules, cannibalization checks, history filtering.
- Modify `trending_seo/test_seo_engine.py`: stale/news rejection, same-intent rejection, distinct-intent allowance.
- Create `trending_seo/seo_intent_history.json`: durable record of successful public SEO intents.
- Modify `trending_seo/pipeline.py`: load history, reject collisions before generation/image/upload, persist history after successful publish, keep `WORDPRESS_STATUS = "publish"`.
- Create `trending_seo/test_evergreen_pipeline.py`: publish-order and no-side-effect tests.
- Modify `trending_seo/test_featured_images.py`: verify SEO image work happens only after eligibility/quality gates and stays SEO-local.
- Modify `.github/workflows/run-trending-seo-pipeline.yml`: run full SEO regression suite and persist intent history.
- Do not modify `.github/workflows/gamerquest.yml`, `.github/workflows/social-test.yml`, `.github/workflows/test-deals.yml`, `automation.py`, `social/`, or `deals/`.

---

### Task 1: Replace trend-heavy scoring with evergreen opportunity scoring

**Files:**
- Modify: `trending_seo/scorer.py`
- Test: `trending_seo/test_scorer.py`

**Interfaces:**
- Consumes: existing `analyze_topic(topic: dict) -> dict` flow.
- Produces: `scores` containing `durability`, `search_intent`, `long_tail_specificity`, `french_relevance`, `competition`, `gamerquest_relevance`, `internal_link_potential`; still produces `total_score`, `decision`, and the existing `seo` object.

- [ ] **Step 1: Write failing score-model tests**

Add tests that assert the new limits total 100 and that an evergreen candidate can score `WRITE` without a high recency score. Example fixture:

```python
scores = {
    "durability": 25,
    "search_intent": 25,
    "long_tail_specificity": 15,
    "french_relevance": 10,
    "competition": 10,
    "gamerquest_relevance": 10,
    "internal_link_potential": 5,
}
self.assertEqual(calculate_total_score(scores), 100)
```

Also add a prompt regression test that calls `build_messages()` and asserts the system prompt contains `durability`, `long_tail_specificity`, `internal_link_potential`, `breaking news`, and `stale event-only`.

- [ ] **Step 2: Run the scorer tests and verify failure**

Run:

```bash
cd trending_seo
python -m unittest test_scorer.py -v
```

Expected: new tests fail because the current scorer still uses `trend_strength` and `freshness`.

- [ ] **Step 3: Implement the evergreen score model**

Replace `SCORE_LIMITS` with:

```python
SCORE_LIMITS = {
    "durability": 25,
    "search_intent": 25,
    "long_tail_specificity": 15,
    "french_relevance": 10,
    "competition": 10,
    "gamerquest_relevance": 10,
    "internal_link_potential": 5,
}
```

Update `build_messages()` so Groq is explicitly told to:

```text
Reward durable informational/commercial-investigation search intent.
Reward specific French long-tail queries a new domain can realistically rank for.
Penalize generic breaking news, broad head terms, stale event-only topics, and thin topics.
Do not reward recency by itself.
```

Keep Python as the only authority calculating totals and keep the existing `WRITE >= 80`, `REVIEW >= 65` thresholds.

- [ ] **Step 4: Run scorer tests and verify pass**

Run the same unittest command. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add trending_seo/scorer.py trending_seo/test_scorer.py
git commit -m "feat: score evergreen SEO opportunities"
```

---

### Task 2: Add deterministic evergreen eligibility and intent normalization

**Files:**
- Modify: `trending_seo/seo_engine.py`
- Test: `trending_seo/test_seo_engine.py`

**Interfaces:**
- Produces: `normalize_search_intent(value: Any) -> str`, `classify_evergreen_intent(topic: dict) -> dict`, `same_search_intent(a: dict, b: dict) -> bool`, `filter_unique_seo_candidates(topics: list, history: dict) -> list`.
- Existing `select_seo_candidates()` remains the public candidate selector and calls the new deterministic filters.

- [ ] **Step 1: Write failing evergreen-rule tests**

Add tests for:

```python
self.assertFalse(classify_evergreen_intent({
    "topic": "State of Play septembre 2026 : toutes les annonces",
    "seo": {"primary_keyword": "state of play septembre 2026 annonces"},
})["eligible"])

self.assertTrue(classify_evergreen_intent({
    "topic": "Jeux comme Elden Ring",
    "seo": {"primary_keyword": "jeux comme Elden Ring"},
})["eligible"])
```

Add same-intent tests:

```python
self.assertTrue(same_search_intent(
    {"seo": {"primary_keyword": "meilleurs jeux coop pc"}},
    {"seo": {"primary_keyword": "les meilleurs jeux coopératifs sur PC"}},
))

self.assertFalse(same_search_intent(
    {"seo": {"primary_keyword": "Elden Ring durée de vie"}},
    {"seo": {"primary_keyword": "jeux comme Elden Ring"}},
))
```

- [ ] **Step 2: Run tests and verify failure**

```bash
cd trending_seo
python -m unittest test_seo_engine.py -v
```

Expected: missing functions / new assertions fail.

- [ ] **Step 3: Implement normalized intent keys and deterministic rules**

Normalize accents/punctuation/common French stopwords and singular/plural noise, while retaining game/platform entities. Implement explicit breaking-news/event markers such as:

```python
EVENT_ONLY_TERMS = {
    "annonce", "annonces", "showcase", "state of play", "gamescom",
    "direct", "trailer", "conférence", "conference", "livestream",
}
```

Implement durable-intent markers such as:

```python
EVERGREEN_PATTERNS = (
    "meilleurs ", "meilleures ", "jeux comme ", "comment ",
    "crossplay", "configuration pc", "durée de vie", "duree de vie",
    "ordre pour jouer", "vaut-il le coup", "alternatives à", "alternatives a",
)
```

The deterministic gate should reject event-only topics unless the primary keyword itself clearly expresses a durable query pattern.

- [ ] **Step 4: Integrate with `select_seo_candidates()`**

Only `WRITE` topics that are evergreen-eligible and not present in history can be returned. Preserve score sorting and `max_articles`.

- [ ] **Step 5: Run tests and verify pass**

Run `test_seo_engine.py -v`. Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add trending_seo/seo_engine.py trending_seo/test_seo_engine.py
git commit -m "feat: gate SEO candidates by durable intent"
```

---

### Task 3: Add persistent search-intent history and cannibalization protection

**Files:**
- Create: `trending_seo/seo_intent_history.json`
- Modify: `trending_seo/seo_engine.py`
- Modify: `trending_seo/pipeline.py`
- Test: `trending_seo/test_seo_engine.py`
- Test: `trending_seo/test_evergreen_pipeline.py`

**Interfaces:**
- History shape:

```json
{
  "version": "1.0",
  "updated_at": null,
  "published": []
}
```

Each published item:

```json
{
  "intent_key": "jeux comme elden ring",
  "primary_keyword": "jeux comme Elden Ring",
  "title": "...",
  "wordpress_url": "https://gamerquestfr.com/.../",
  "wordpress_post_id": 123,
  "published_at": "2026-09-07T00:00:00+00:00"
}
```

- Produces: `load_intent_history(path) -> dict`, `record_published_intent(history, article, brief, wp_result) -> dict`.

- [ ] **Step 1: Write failing history tests**

Cover:
- same intent in history is rejected before article generation;
- distinct query for same game is allowed;
- successful WordPress result appends one history record;
- failed WordPress result appends nothing.

- [ ] **Step 2: Run tests and verify failure**

```bash
cd trending_seo
python -m unittest test_seo_engine.py test_evergreen_pipeline.py -v
```

- [ ] **Step 3: Implement history loading and record creation**

Use safe empty defaults if file is absent or malformed; do not crash a run because history is unavailable. History is only mutated after a confirmed 2xx WordPress creation whose returned status equals `publish`.

- [ ] **Step 4: Add pre-generation collision check in `pipeline.main()`**

Required ordering:

```text
load scored topics
load intent history
select candidate
build brief
reject same intent
research/generate
validate article
find/upload image
publish WordPress
persist successful intent
```

No Groq article-generation call and no WordPress media upload may happen for a duplicate intent.

- [ ] **Step 5: Run tests and verify pass**

Run the Task 3 unittest command. Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add trending_seo/seo_intent_history.json trending_seo/seo_engine.py trending_seo/pipeline.py trending_seo/test_seo_engine.py trending_seo/test_evergreen_pipeline.py
git commit -m "feat: persist SEO intent history"
```

---

### Task 4: Make research and writing explicitly evergreen-first while preserving fact safety

**Files:**
- Modify: `trending_seo/researcher.py`
- Modify: `trending_seo/pipeline.py`
- Test: `trending_seo/test_researcher.py`
- Test: `trending_seo/test_evergreen_pipeline.py`

**Interfaces:**
- Existing researcher fact-pack APIs remain intact.
- `build_discovery_query(topic, claim="")` should use the primary search keyword and evergreen intent rather than automatically appending `official announcement news` for every no-claim query.

- [ ] **Step 1: Write failing research-query tests**

Example:

```python
query = build_discovery_query({
    "topic": "Jeux comme Elden Ring",
    "seo": {"primary_keyword": "jeux comme Elden Ring"},
})
self.assertIn("jeux comme Elden Ring", query)
self.assertNotIn("official announcement news", query.lower())
```

Keep existing claim-verification tests unchanged.

- [ ] **Step 2: Run tests and verify failure**

```bash
cd trending_seo
python -m unittest test_researcher.py -v
```

- [ ] **Step 3: Update evergreen research discovery**

For no-claim discovery, build the query from the `primary_keyword` plus one neutral research modifier such as `guide avis comparatif informations`. For hard factual claims (date, price, platform, feature), keep the existing source-verification and `CONFIRMED` fact-pack behavior.

- [ ] **Step 4: Strengthen `pipeline.build_article_prompt()`**

Require:

```text
- answer the primary search intent immediately;
- create a durable resource, not a recap of a recent event;
- use the verified research pack for precise dates/prices/platform claims;
- never invent hard facts;
- include practical sections that map to the actual query;
- avoid generic filler and keyword stuffing.
```

- [ ] **Step 5: Run researcher + evergreen pipeline tests**

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add trending_seo/researcher.py trending_seo/pipeline.py trending_seo/test_researcher.py trending_seo/test_evergreen_pipeline.py
git commit -m "feat: research evergreen search intent"
```

---

### Task 5: Enforce publish ordering and SEO-only featured image behavior

**Files:**
- Modify: `trending_seo/pipeline.py`
- Modify: `trending_seo/test_featured_images.py`
- Modify: `trending_seo/test_evergreen_pipeline.py`

**Interfaces:**
- Existing `extract_relevant_image_url()`, `find_relevant_source_image()`, and `upload_featured_image()` remain SEO-pipeline functions.
- `create_wordpress_draft()` may keep its historical name, but it must continue sending `status=WORDPRESS_STATUS`, where `WORDPRESS_STATUS == "publish"`.

- [ ] **Step 1: Write failing call-order tests**

Use mocks that explode if image lookup/upload or WordPress publish is reached when:
- candidate intent is duplicate;
- `validate_seo_article()` returns `publishable=False`;
- research/factual gate fails.

Also assert that a valid path calls article validation before image upload and image upload before WordPress publish.

- [ ] **Step 2: Run tests and verify failure**

```bash
cd trending_seo
python -m unittest test_featured_images.py test_evergreen_pipeline.py -v
```

- [ ] **Step 3: Refactor only the SEO pipeline ordering**

Do not import or modify News/social image code. The valid publish sequence must be:

```text
unique intent -> sufficient research -> generated article -> SEO quality passed -> relevant source image -> WP media upload -> WP post publish -> history persistence
```

If relevant image extraction/upload fails, fail closed and do not publish a text-only SEO page.

- [ ] **Step 4: Preserve automatic publish regression**

Keep:

```python
WORDPRESS_STATUS = "publish"
```

and preserve the existing regression in `test_pipeline_publish_mode.py`.

- [ ] **Step 5: Run tests and verify pass**

Run:

```bash
cd trending_seo
python -m unittest test_featured_images.py test_pipeline_publish_mode.py test_evergreen_pipeline.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add trending_seo/pipeline.py trending_seo/test_featured_images.py trending_seo/test_evergreen_pipeline.py
git commit -m "feat: gate SEO publishing before images and WordPress"
```

---

### Task 6: Wire the full regression suite and persist history in GitHub Actions

**Files:**
- Modify: `.github/workflows/run-trending-seo-pipeline.yml`
- Test: `trending_seo/test_pipeline_publish_mode.py`

**Interfaces:**
- Workflow continues to execute `python trending_seo/pipeline.py` with WordPress credentials.
- Workflow persists `trending_seo/seo_intent_history.json` with existing SEO state.

- [ ] **Step 1: Write a failing workflow regression**

Extend `test_pipeline_publish_mode.py` to assert the workflow contains:

```text
test_scorer.py
test_seo_engine.py
test_researcher.py
test_featured_images.py
test_evergreen_pipeline.py
test_pipeline_publish_mode.py
trending_seo/seo_intent_history.json
python trending_seo/pipeline.py
```

and does not contain a forced draft override.

- [ ] **Step 2: Run test and verify failure**

```bash
cd trending_seo
python -m unittest test_pipeline_publish_mode.py -v
```

- [ ] **Step 3: Update workflow test step**

Run all relevant SEO tests before the pipeline:

```yaml
- name: Run Evergreen SEO regression tests
  working-directory: trending_seo
  run: |
    python -m unittest \
      test_scorer.py \
      test_seo_engine.py \
      test_researcher.py \
      test_featured_images.py \
      test_evergreen_pipeline.py \
      test_pipeline_publish_mode.py \
      -v
```

Add:

```bash
git add trending_seo/seo_intent_history.json 2>/dev/null || true
```

to the state-save step.

Do not add schedules yet; the existing workflow remains manually triggerable until a successful production smoke test proves the new engine behavior. Automatic publishing refers to WordPress post status, not to scheduling cadence.

- [ ] **Step 4: Run the complete local SEO suite**

```bash
cd trending_seo
python -m unittest \
  test_scorer.py \
  test_seo_engine.py \
  test_researcher.py \
  test_writer.py \
  test_featured_images.py \
  test_evergreen_pipeline.py \
  test_pipeline_publish_mode.py \
  -v
```

Expected: PASS.

- [ ] **Step 5: Verify untouched automation files**

Compare the implementation base commit against HEAD and confirm there are zero changes to:

```text
automation.py
.github/workflows/gamerquest.yml
.github/workflows/social-test.yml
.github/workflows/test-deals.yml
social/
deals/
```

- [ ] **Step 6: Commit**

```bash
git add .github/workflows/run-trending-seo-pipeline.yml trending_seo/test_pipeline_publish_mode.py
git commit -m "ci: verify evergreen SEO automation"
```

---

### Task 7: Production smoke test and evidence-based verification

**Files:**
- Read: GitHub Actions logs for `Run Trending SEO Pipeline`
- Inspect: `trending_seo/pipeline_result.json`
- Inspect: `trending_seo/seo_intent_history.json`

**Interfaces:**
- No code changes are required unless the smoke test exposes a concrete defect.

- [ ] **Step 1: Trigger one manual `Run Trending SEO Pipeline` workflow**

Use the current `main` branch after all regression tests are committed.

- [ ] **Step 2: Verify the test step succeeds before pipeline execution**

Expected: all Evergreen SEO regression tests PASS.

- [ ] **Step 3: Inspect pipeline behavior**

Acceptable outcomes:

```text
A) no eligible unique evergreen topic -> safe stop, no WordPress post
B) eligible topic but insufficient evidence/image/quality -> safe stop, no WordPress post
C) all gates pass -> exactly one public WordPress post with a featured image
```

Any public post must have `status=publish` and the returned URL/post ID must be written to `pipeline_result.json` and appended to `seo_intent_history.json`.

- [ ] **Step 4: Re-run candidate selection against the recorded history**

The just-published intent must be rejected on the next run even if its source/topic ID changes.

- [ ] **Step 5: Verify untouched automations are still healthy**

Check the most recent News, Social, and Deals workflow definitions/runs independently. Do not alter them as part of the SEO smoke test.

- [ ] **Step 6: Final verification commit only if a state file changed through the workflow**

The workflow itself should commit state changes. Do not create a manual code commit merely to mark success.

---

## Self-Review

- Spec coverage: topic strategy, new scoring, persistent history, cannibalization, research safety, article quality, isolated SEO images, automatic WordPress publish, and untouched News/Social/Deals are each mapped to a task.
- Placeholder scan: no TBD/TODO/"implement later" placeholders remain.
- Type consistency: intent history and helper names are consistent across Tasks 2, 3, 5, and 6.
- Risk control: WordPress publishing remains automatic, but no media or post is created until deterministic and content-quality gates pass.
