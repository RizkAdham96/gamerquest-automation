# GamerQuest Acquisition Shadow Engine Design

## Goal
Build a zero-cost, non-invasive acquisition layer that ranks traffic opportunities without changing or blocking the existing publishing automations.

## Safety boundary
- Existing production workflows remain untouched in phase 1.
- The acquisition engine reads existing repository outputs only.
- It never publishes to WordPress, social platforms, or the existing news feed.
- Failure in the acquisition workflow must not affect News, Deals, Reviews, or Social workflows.
- All outputs are written under `acquisition/`.

## Inputs
The shadow engine reads:
- `trending_seo/intel/topics.json` for researched SEO opportunities.
- `trending_seo/scored_topics.json` when existing evergreen SEO scoring is available.
- `gamerquest-news-feed.json` to detect already-covered topics.
- `gamerquest-deals-feed.json` for current deal/free-game opportunities.
- `state/news_topic_history.json` to avoid historical cannibalization.

Missing optional inputs are treated as empty instead of failing the run.

## Components
### 1. Candidate collector
Normalize existing SEO intel, scored topics, news, and deals into a common candidate schema. Candidate records include id, title, source type, keywords, freshness, existing score, and source evidence.

### 2. Deterministic acquisition scorer
Score each candidate to 100 using only repository evidence:
- Specificity / long-tail fit: 25
- Search-intent strength: 20
- Freshness / time sensitivity: 15
- Competition proxy: 15
- GamerQuest fit: 10
- Distribution potential: 10
- Internal-link potential: 5

The scorer must not invent search volume. Broad head terms are penalized. Specific player questions, platform combinations, free-game windows, patch/fix intent, and date/platform intent receive stronger scores.

### 3. Cannibalization guard
Before a candidate can be recommended, compare normalized topic terms with the current news feed and persistent topic history. Strong same-subject overlap lowers or blocks the opportunity unless it is a clearly different intent.

### 4. Shadow queue
Write `acquisition/shadow_queue.json` containing ranked candidates and one of:
- `PRIORITIZE` for score >= 75
- `WATCH` for score 55-74
- `SKIP` for score < 55

Each item must explain its score so the system is auditable.

### 5. Isolated scheduled workflow
Create `.github/workflows/acquisition-shadow.yml` with manual dispatch and a safe schedule. It runs tests first, then the shadow engine, then commits only acquisition output when changed. It uses no paid API and no secrets.

## Success criteria
- Existing production workflow files are unchanged.
- Acquisition workflow succeeds independently.
- Unit tests cover scoring, broad-topic penalty, specific-intent reward, historical duplicate suppression, and missing-input behavior.
- A real shadow queue is generated from current repository data.
- No WordPress or social publishing occurs.

## Phase 2, not part of this build
After several shadow runs prove useful, high-scoring opportunities may be allowed to feed existing content generation. That integration requires a separate explicit design and regression gate.