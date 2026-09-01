import unittest

from seo_engine import (
    select_seo_candidates,
    build_seo_brief,
    validate_seo_article,
)


class TestSEOEngine(unittest.TestCase):

    def test_write_topic_is_selected_without_confirmed_facts(self):
        scored_data = {
            "topics": [
                {
                    "id": "topic-1",
                    "topic": "Test Game",
                    "decision": "WRITE",
                    "total_score": 84,
                    "seo": {
                        "primary_keyword": "Test Game guide",
                        "secondary_keywords": [
                            "Test Game astuces",
                            "Test Game debutant",
                        ],
                        "search_intent_type": "information",
                        "recommended_angle": "Guide utile pour les joueurs.",
                        "suggested_title": "Test Game : guide complet",
                    },
                }
            ]
        }

        result = select_seo_candidates(
            scored_data,
            max_articles=1,
        )

        self.assertEqual(len(result), 1)
        self.assertEqual(
            result[0]["id"],
            "topic-1",
        )

    def test_review_and_reject_topics_are_not_selected(self):
        scored_data = {
            "topics": [
                {
                    "id": "review-topic",
                    "topic": "Review Topic",
                    "decision": "REVIEW",
                    "total_score": 74,
                    "seo": {},
                },
                {
                    "id": "reject-topic",
                    "topic": "Reject Topic",
                    "decision": "REJECT",
                    "total_score": 50,
                    "seo": {},
                },
            ]
        }

        result = select_seo_candidates(
            scored_data,
            max_articles=2,
        )

        self.assertEqual(result, [])

    def test_seo_brief_uses_search_intent_and_keywords(self):
        topic = {
            "id": "topic-1",
            "topic": "Test Game",
            "decision": "WRITE",
            "total_score": 85,
            "seo": {
                "primary_keyword": "Test Game guide",
                "secondary_keywords": [
                    "Test Game astuces",
                    "Test Game debutant",
                ],
                "search_intent_type": "information",
                "recommended_angle": "Guide pratique pour debutants.",
                "suggested_title": "Test Game : guide complet pour debuter",
            },
        }

        brief = build_seo_brief(topic)

        self.assertEqual(
            brief["status"],
            "SEO_BRIEF_READY",
        )

        self.assertEqual(
            brief["primary_keyword"],
            "Test Game guide",
        )

        self.assertEqual(
            brief["search_intent"],
            "information",
        )

        self.assertIn(
            "Test Game astuces",
            brief["secondary_keywords"],
        )

        self.assertTrue(
            brief["suggested_title"]
        )

    def test_seo_brief_does_not_require_researcher_fact_pack(self):
        topic = {
            "id": "topic-1",
            "topic": "Test Game",
            "decision": "WRITE",
            "total_score": 82,
            "seo": {
                "primary_keyword": "Test Game",
                "secondary_keywords": [],
                "search_intent_type": "information",
                "recommended_angle": "Guide SEO.",
                "suggested_title": "Test Game : tout savoir",
            },
        }

        brief = build_seo_brief(topic)

        self.assertEqual(
            brief["status"],
            "SEO_BRIEF_READY",
        )

        self.assertNotIn(
            "confirmed_facts",
            brief,
        )

        self.assertNotIn(
            "research_status",
            brief,
        )

    def test_good_seo_article_passes_quality_check(self):
        article = {
            "title": "Test Game guide : bien debuter en 2026",
            "meta_description": (
                "Decouvrez notre Test Game guide avec les conseils essentiels "
                "pour bien debuter, progresser et eviter les erreurs classiques."
            ),
            "content": (
                "<p>Ce Test Game guide repond directement aux questions des joueurs.</p>"
                "<h2>Comment bien debuter dans Test Game ?</h2>"
                "<p>Commencez par comprendre les mecanismes essentiels et vos objectifs.</p>"
                "<h2>Les meilleures astuces pour progresser</h2>"
                "<p>Adaptez votre strategie, testez plusieurs approches et analysez vos erreurs.</p>"
                "<h2>Questions frequentes sur Test Game</h2>"
                "<p>Voici les reponses aux questions les plus recherchees par les joueurs.</p>"
            ),
        }

        brief = {
            "primary_keyword": "Test Game guide",
            "secondary_keywords": [
                "Test Game astuces",
            ],
            "search_intent": "information",
        }

        result = validate_seo_article(
            article,
            brief,
        )

        self.assertEqual(
            result["status"],
            "SEO_QUALITY_PASSED",
        )

        self.assertTrue(
            result["publishable"]
        )

    def test_article_missing_primary_keyword_fails(self):
        article = {
            "title": "Un guide pour bien debuter",
            "meta_description": (
                "Conseils pour commencer facilement "
                "et progresser."
            ),
            "content": (
                "<h2>Comment debuter ?</h2>"
                "<p>Voici plusieurs conseils utiles.</p>"
                "<h2>Conseils avances</h2>"
                "<p>Continuez a progresser.</p>"
            ),
        }

        brief = {
            "primary_keyword": "Test Game guide",
            "secondary_keywords": [],
            "search_intent": "information",
        }

        result = validate_seo_article(
            article,
            brief,
        )

        self.assertEqual(
            result["status"],
            "SEO_QUALITY_FAILED",
        )

        self.assertFalse(
            result["publishable"]
        )

        self.assertIn(
            "primary_keyword",
            result["issues"],
        )

    def test_article_without_h2_structure_fails(self):
        article = {
            "title": "Test Game guide : bien debuter",
            "meta_description": (
                "Test Game guide pour comprendre "
                "le jeu et progresser rapidement."
            ),
            "content": (
                "<p>Test Game guide avec plusieurs "
                "conseils utiles pour les joueurs.</p>"
            ),
        }

        brief = {
            "primary_keyword": "Test Game guide",
            "secondary_keywords": [],
            "search_intent": "information",
        }

        result = validate_seo_article(
            article,
            brief,
        )

        self.assertEqual(
            result["status"],
            "SEO_QUALITY_FAILED",
        )

        self.assertFalse(
            result["publishable"]
        )

        self.assertIn(
            "h2_structure",
            result["issues"],
        )


if __name__ == "__main__":
    unittest.main()
