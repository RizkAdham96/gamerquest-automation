import json
import unittest
from unittest.mock import patch

from scorer import analyze_topic, build_messages, calculate_total_score, get_decision


class TestTrendingSeoScorer(unittest.TestCase):
    """Regression coverage for the evergreen-first scoring model."""

    def evergreen_scores(self):
        return {
            "durability": 25,
            "search_intent": 25,
            "long_tail_specificity": 15,
            "french_relevance": 10,
            "competition": 10,
            "gamerquest_relevance": 10,
            "internal_link_potential": 5,
        }

    def test_calculate_total_score_evergreen_model(self):
        self.assertEqual(calculate_total_score(self.evergreen_scores()), 100)

    def test_evergreen_candidate_can_write_without_recency_score(self):
        scores = self.evergreen_scores()
        self.assertNotIn("freshness", scores)
        self.assertNotIn("trend_strength", scores)
        self.assertEqual(get_decision(calculate_total_score(scores)), "WRITE")

    def test_prompt_is_evergreen_first(self):
        messages = build_messages({"topic": "Jeux comme Elden Ring"})
        prompt = messages[0]["content"].lower()
        for term in (
            "durability",
            "long_tail_specificity",
            "internal_link_potential",
            "breaking news",
            "stale event-only",
        ):
            self.assertIn(term, prompt)

    def test_write_threshold(self):
        self.assertEqual(get_decision(80), "WRITE")
        self.assertEqual(get_decision(100), "WRITE")

    def test_review_threshold(self):
        self.assertEqual(get_decision(65), "REVIEW")
        self.assertEqual(get_decision(79), "REVIEW")

    def test_reject_threshold(self):
        self.assertEqual(get_decision(0), "REJECT")
        self.assertEqual(get_decision(64), "REJECT")

    def test_total_is_calculated_by_python(self):
        scores = {
            "durability": 20,
            "search_intent": 22,
            "long_tail_specificity": 12,
            "french_relevance": 9,
            "competition": 6,
            "gamerquest_relevance": 9,
            "internal_link_potential": 5,
        }
        self.assertEqual(calculate_total_score(scores), 83)
        self.assertEqual(get_decision(calculate_total_score(scores)), "WRITE")

    def test_scored_topic_keeps_verified_image_sources(self):
        source = {
            "type": "official",
            "url": "https://games.example/witcher-3",
            "title": "The Witcher 3 Remastered",
            "evidence": "Official announcement.",
        }
        ai_result = {
            "scores": self.evergreen_scores(),
            "primary_keyword": "The Witcher 3 Remastered guide",
            "secondary_keywords": [],
            "search_intent_type": "information",
            "recommended_angle": "Guide",
            "suggested_title": "The Witcher 3 Remastered : guide",
            "reasoning": "Durable opportunity.",
        }
        with patch("scorer.groq_chat", return_value=json.dumps(ai_result)):
            result = analyze_topic({
                "id": "witcher-3",
                "topic": "The Witcher 3 Remastered",
                "sources": [source],
            })
        self.assertEqual(result["sources"], [source])


if __name__ == "__main__":
    unittest.main()
