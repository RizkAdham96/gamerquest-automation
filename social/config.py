# GamerQuest Social Automation
# Central configuration for the social-content system.

BRAND_NAME = "GamerQuest"
WEBSITE_URL = "https://gamerquest.fr"

POSTS_PER_WEEK = 2

RECENT_POST_MEMORY = 20

MINIMUM_PUBLISH_SCORE = 65

CAROUSEL_MIN_SLIDES = 3
CAROUSEL_MAX_SLIDES = 3

SOCIAL_FORMATS = [
    "breaking_news",
    "deal_alert",
    "free_game",
    "ranking",
    "recommendation",
    "comparison",
    "quiz",
    "did_you_know",
    "upcoming_games",
    "controversy",
    "nostalgia",
    "prediction",
    "challenge",
    "community",
    "guessing_game",
    "explainer",
]

SCORING_WEIGHTS = {
    "freshness": 20,
    "click_potential": 20,
    "curiosity": 15,
    "shareability": 15,
    "originality": 20,
    "gamerquest_relevance": 10,
}
