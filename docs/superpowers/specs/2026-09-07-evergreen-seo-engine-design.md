# GamerQuest Evergreen SEO Engine Design

## Goal

Keep GamerQuest fully automatic while changing the separate Trending SEO pipeline from mostly short-lived gaming news into a search-demand engine that produces durable French gaming pages capable of earning organic traffic over weeks and months.

## Non-negotiable constraints

- Main News automation remains unchanged and continues its current schedule.
- Automatic WordPress publishing remains enabled for the SEO pipeline after validation gates pass.
- Existing News image generation remains untouched.
- Existing social automation and social image generation remain untouched.
- Deals automation remains untouched.
- The SEO pipeline may reuse existing infrastructure, but it must not modify the News feed logic or social/deals workflows.
- Maximum SEO output remains conservative: one SEO article per SEO run unless explicitly changed later.

## New SEO pipeline behavior

The Trending SEO pipeline becomes an evergreen/search-intent pipeline.

Flow:

1. Discover candidate French gaming search intents.
2. Score candidates for durable search value and new-domain attainability.
3. Reject stale or purely breaking-news topics unless they have durable search intent.
4. Reject topics that overlap an existing GamerQuest article or target the same search intent.
5. Research the selected topic with trustworthy sources.
6. Generate a complete French SEO article built around the selected intent.
7. Run factual and content-quality checks.
8. Add contextual internal links to relevant GamerQuest content.
9. Create a relevant featured image through an isolated SEO image path, reusing safe image-generation components where appropriate without changing the News/social image systems.
10. Automatically publish to WordPress only if every gate passes.
11. Persist the selected/published intent in a durable history so future runs cannot recreate the same page after short feed windows expire.

## Topic strategy

Prefer long-tail, durable, useful French gaming searches such as:

- meilleurs jeux coop PC
- meilleurs jeux gratuits PC
- jeux comme Elden Ring
- jeux crossplay PS5 PC
- meilleurs jeux solo PS5
- comment jouer en crossplay sur [jeu]
- configuration PC recommandée [jeu]
- ordre pour jouer à [série]
- durée de vie [jeu]
- [jeu] vaut-il le coup
- meilleures alternatives à [jeu]

The engine should prefer topics with clear informational/commercial investigation intent, useful shelf life, French relevance, and realistic competition for a new site.

## Scoring changes

The scorer should explicitly reward:

- durable search intent
- long-tail specificity
- French relevance
- usefulness to gamers
- realistic competitiveness for a new domain
- internal-link potential
- topic freshness where freshness matters

It should penalize:

- generic breaking news
- broad head terms dominated by major publishers
- topics already covered by GamerQuest
- substantially similar search intents
- stale event-only topics
- thin topics that cannot support a genuinely useful article

## Duplicate and cannibalization protection

Create persistent SEO intent history separate from the rolling News feed.

Before writing, compare the candidate against:

- persistent SEO history
- current SEO state files
- known GamerQuest URLs/topics available to the pipeline
- relevant News feed titles/slugs where useful

Reject a candidate when it would compete with an existing GamerQuest page for substantially the same search intent.

## Publishing rule

Automatic publishing is the desired final behavior.

The WordPress post is created with `status=publish` only after:

- topic is unique
- research is sufficient
- factual sanity checks pass
- article quality checks pass
- featured image generation succeeds or the pipeline has an explicitly safe image fallback

A failed gate means no public article is created.

## Image handling

SEO article images must be isolated from existing social and News image behavior.

Preferred approach:

- reuse tested low-level image helpers where safe
- write SEO assets to their own predictable location/name
- generate/select the image only after duplicate and quality checks
- ensure image is related to the article topic
- preserve current News image generation behavior exactly

## Tests required before production-code changes are considered complete

Add regression tests covering at least:

1. durable evergreen intent scores above equivalent generic breaking-news intent
2. stale event-only topic is rejected
3. long-tail French gaming query receives positive scoring preference
4. existing/similar GamerQuest intent is rejected
5. distinct intent about the same game is allowed
6. published intent is persisted so it cannot be regenerated later
7. WordPress status remains `publish`
8. WordPress publish function is not called when a quality/duplicate gate fails
9. SEO image generation occurs only after content gates pass
10. existing News/social/deals files and workflows are not modified by this feature

## Rollout

Phase 1: implement scoring, intent history, deduplication and tests.

Phase 2: integrate evergreen research/writing behavior and SEO featured-image flow.

Phase 3: verify the automatic publish path in GitHub Actions and inspect the generated article/state before declaring the system healthy.

The existing News automation continues operating throughout this rollout.

## Success criteria

The system is successful when it automatically creates distinct, useful French gaming pages aimed at durable search demand while continuing to publish without manual approval and without interfering with News, social, deals, or their image pipelines.
