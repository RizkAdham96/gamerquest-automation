import unittest
from unittest.mock import patch

import pipeline


class TestPipelineResearchGate(unittest.TestCase):
    def test_research_without_evidence_is_not_sufficient(self):
        self.assertFalse(pipeline.research_context_is_sufficient({
            "usable_evidence": [],
            "fact_pack": {"confirmed_facts": []},
        }))

    def test_research_with_usable_evidence_is_sufficient(self):
        self.assertTrue(pipeline.research_context_is_sufficient({
            "usable_evidence": [{"url": "https://example.com", "text": "Useful source"}],
            "fact_pack": {"confirmed_facts": []},
        }))

    def test_article_prompt_contains_verified_research_context(self):
        prompt = pipeline.build_article_prompt(
            {
                "topic": "Jeux comme Elden Ring",
                "primary_keyword": "jeux comme Elden Ring",
                "secondary_keywords": [],
                "search_intent": "information",
                "recommended_angle": "Comparatif utile",
                "suggested_title": "Jeux comme Elden Ring",
            },
            research_context={
                "usable_evidence": [{
                    "url": "https://example.com/source",
                    "title": "Source fiable",
                    "text": "Elden Ring est un action-RPG.",
                }],
                "fact_pack": {
                    "confirmed_facts": [{
                        "claim": "Elden Ring est un action-RPG.",
                        "sources": ["https://example.com/source"],
                    }],
                    "blocked_claims": [],
                },
            },
        )
        self.assertIn("https://example.com/source", prompt)
        self.assertIn("Elden Ring est un action-RPG", prompt)
        self.assertIn("n'invente", prompt.lower())

    def test_insufficient_research_stops_before_generation_and_images(self):
        topic = {
            "id": "elden",
            "topic": "Jeux comme Elden Ring",
            "total_score": 90,
            "seo": {
                "primary_keyword": "jeux comme Elden Ring",
                "search_intent_type": "information",
                "suggested_title": "Jeux comme Elden Ring",
            },
        }
        wp_config = {
            "base_url": "https://gamerquestfr.com",
            "username": "user",
            "application_password": "secret",
        }
        with patch.object(
            pipeline,
            "build_research_context",
            return_value={"usable_evidence": [], "fact_pack": {"confirmed_facts": []}},
        ), patch.object(
            pipeline,
            "generate_seo_article",
            side_effect=AssertionError("generation must not run"),
        ), patch.object(
            pipeline,
            "find_relevant_source_image",
            side_effect=AssertionError("image must not run"),
        ):
            result = pipeline.process_seo_topic(topic, wp_config)

        self.assertEqual(result["status"], "BLOCKED_INSUFFICIENT_RESEARCH")
        self.assertFalse(result["published"])


if __name__ == "__main__":
    unittest.main()
