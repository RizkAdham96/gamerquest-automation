import unittest

from seo_engine import (
    build_seo_brief,
    classify_evergreen_intent,
    filter_unique_seo_candidates,
    normalize_search_intent,
    same_search_intent,
    select_seo_candidates,
    validate_seo_article,
)


class TestSEOEngine(unittest.TestCase):
    def evergreen_topic(self, keyword="jeux comme Elden Ring", score=90):
        return {
            "id": "topic-1",
            "topic": keyword,
            "decision": "WRITE",
            "total_score": score,
            "seo": {
                "primary_keyword": keyword,
                "secondary_keywords": [],
                "search_intent_type": "information",
                "recommended_angle": "Guide durable",
                "suggested_title": keyword,
            },
        }

    def test_event_only_topic_is_not_evergreen(self):
        result = classify_evergreen_intent({
            "topic": "State of Play septembre 2026 : toutes les annonces",
            "seo": {"primary_keyword": "state of play septembre 2026 annonces"},
        })
        self.assertFalse(result["eligible"])

    def test_durable_query_is_evergreen(self):
        self.assertTrue(classify_evergreen_intent(self.evergreen_topic())["eligible"])

    def test_normalize_search_intent_handles_french_variants(self):
        a = normalize_search_intent("Les meilleurs jeux coopératifs sur PC")
        b = normalize_search_intent("meilleurs jeux coop pc")
        self.assertEqual(a, b)

    def test_same_search_intent_rejects_reworded_keyword(self):
        self.assertTrue(same_search_intent(
            {"seo": {"primary_keyword": "meilleurs jeux coop pc"}},
            {"seo": {"primary_keyword": "les meilleurs jeux coopératifs sur PC"}},
        ))

    def test_distinct_intent_for_same_game_is_allowed(self):
        self.assertFalse(same_search_intent(
            {"seo": {"primary_keyword": "Elden Ring durée de vie"}},
            {"seo": {"primary_keyword": "jeux comme Elden Ring"}},
        ))

    def test_history_collision_is_filtered(self):
        topic = self.evergreen_topic()
        history = {"published": [{"intent_key": normalize_search_intent("jeux comme Elden Ring")}]}
        self.assertEqual(filter_unique_seo_candidates([topic], history), [])

    def test_write_topic_is_selected_without_confirmed_facts(self):
        result = select_seo_candidates({"topics": [self.evergreen_topic()]}, max_articles=1)
        self.assertEqual(len(result), 1)

    def test_review_and_reject_topics_are_not_selected(self):
        topics = [
            {**self.evergreen_topic("comment jouer à Elden Ring"), "decision": "REVIEW"},
            {**self.evergreen_topic("Elden Ring durée de vie"), "decision": "REJECT"},
        ]
        self.assertEqual(select_seo_candidates({"topics": topics}, max_articles=2), [])

    def test_seo_brief_uses_search_intent_and_keywords(self):
        brief = build_seo_brief(self.evergreen_topic())
        self.assertEqual(brief["status"], "SEO_BRIEF_READY")
        self.assertEqual(brief["primary_keyword"], "jeux comme Elden Ring")
        self.assertEqual(brief["search_intent"], "information")

    def test_good_seo_article_passes_quality_check(self):
        article = {
            "title": "Jeux comme Elden Ring : nos recommandations",
            "meta_description": "Découvrez les jeux comme Elden Ring à essayer selon vos envies.",
            "content": (
                "<p>Voici les meilleurs jeux comme Elden Ring selon le type d'expérience recherché.</p>"
                "<h2>Pour le combat exigeant</h2><p>Choisissez selon vos priorités.</p>"
                "<h2>Pour l'exploration</h2><p>Comparez les mondes et les systèmes.</p>"
            ),
        }
        result = validate_seo_article(article, {"primary_keyword": "jeux comme Elden Ring"})
        self.assertTrue(result["publishable"])

    def test_article_missing_primary_keyword_fails(self):
        article = {
            "title": "Un guide utile",
            "meta_description": "Conseils utiles.",
            "content": "<h2>Débuter</h2><p>Conseils.</p><h2>Progresser</h2><p>Astuces.</p>",
        }
        result = validate_seo_article(article, {"primary_keyword": "jeux comme Elden Ring"})
        self.assertFalse(result["publishable"])
        self.assertIn("primary_keyword", result["issues"])


if __name__ == "__main__":
    unittest.main()
