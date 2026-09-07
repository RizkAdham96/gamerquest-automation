import json
import unittest
from unittest.mock import patch

from scorer import analyze_topic, calculate_total_score, get_decision


class TestTrendingSeoScorer(unittest.TestCase):

    def test_calculate_total_score(self):
        scores = {
            "trend_strength": 25,
            "search_intent": 25,
            "freshness": 20,
            "french_relevance": 15,
            "competition": 10,
            "gamerquest_relevance": 5,
        }

        self.assertEqual(
            calculate_total_score(scores),
            100,
        )

    def test_write_threshold(self):
        self.assertEqual(
            get_decision(80),
            "WRITE",
        )

        self.assertEqual(
            get_decision(100),
            "WRITE",
        )

    def test_review_threshold(self):
        self.assertEqual(
            get_decision(65),
            "REVIEW",
        )

        self.assertEqual(
            get_decision(79),
            "REVIEW",
        )

    def test_reject_threshold(self):
        self.assertEqual(
            get_decision(0),
            "REJECT",
        )

        self.assertEqual(
            get_decision(64),
            "REJECT",
        )

    def test_total_is_calculated_by_python(self):
        scores = {
            "trend_strength": 20,
            "search_intent": 22,
            "freshness": 18,
            "french_relevance": 12,
            "competition": 6,
            "gamerquest_relevance": 5,
        }

        self.assertEqual(
            calculate_total_score(scores),
            83,
        )

        self.assertEqual(
            get_decision(
                calculate_total_score(scores)
            ),
            "WRITE",
        )

    def test_scored_topic_keeps_verified_image_sources(self):
        source = {
            "type": "official",
            "url": "https://games.example/witcher-3",
            "title": "The Witcher 3 Remastered",
            "evidence": "Official announcement.",
        }
        ai_result = {
            "scores": {
                "trend_strength": 25,
                "search_intent": 25,
                "freshness": 20,
                "french_relevance": 15,
                "competition": 10,
                "gamerquest_relevance": 5,
            },
            "primary_keyword": "The Witcher 3 Remastered",
            "secondary_keywords": [],
            "search_intent_type": "information",
            "recommended_angle": "Guide",
            "suggested_title": "The Witcher 3 Remastered",
            "reasoning": "Strong opportunity.",
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
