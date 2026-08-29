import unittest

from scorer import calculate_total_score, get_decision


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


if __name__ == "__main__":
    unittest.main()
