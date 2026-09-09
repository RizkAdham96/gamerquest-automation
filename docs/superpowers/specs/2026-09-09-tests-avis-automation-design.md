# Tests & Avis Automation Design

## Goal
Populate `https://gamerquestfr.com/category/tests/` automatically with trustworthy game review pages at €0.

## Architecture
The review pipeline discovers game candidates from GamerQuest's existing deals and news feeds, then resolves each game against Steam. Steam supplies free metadata, header artwork, and aggregate player-review counts. GamerQuest calculates a transparent 0–5 player-review index from Steam positive-review percentage; it never presents this automated score as a hands-on editorial review.

The pipeline publishes or updates WordPress posts through the standard authenticated WordPress REST API already used by GamerQuest. Posts are assigned to the existing category slug `tests`, receive Steam artwork as featured media when upload succeeds, and use a deterministic Steam-app-based slug so repeat runs update rather than duplicate a game.

## First-release scope
- Discover up to 3 relevant games per run from the existing deals/news feeds.
- Steam store search for game resolution.
- Steam app details for name, description, developer, genre, release date, platforms, and header image.
- Steam aggregate player-review counts for positive percentage and review total.
- GamerQuest player score = positive percentage / 20, rounded to one decimal.
- French review page that clearly labels the score as player-review based.
- Featured image upload to WordPress.
- Publish/update directly into WordPress category slug `tests`.
- Daily scheduled workflow plus manual workflow dispatch.
- No paid APIs, paid hosting, or paid AI.

## Reliability rules
- Missing Steam match: skip candidate.
- Missing Steam review data: skip candidate.
- Image upload failure must not block text publication.
- Failure for one game must not block other candidates.
- If all attempted candidates error, the workflow fails visibly.
- Existing post is updated by deterministic slug rather than duplicated.

## Future enrichment
Epic ratings may be added only when a stable, free, reliable source is available. It is not required for the first release and must not block Steam-based publication.
