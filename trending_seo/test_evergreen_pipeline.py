import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pipeline
from seo_engine import normalize_search_intent, select_seo_candidates


class TestEvergreenPipeline(unittest.TestCase):
    """Regression coverage for durable SEO publish history."""

    def test_missing_history_loads_safe_empty_default(self):
        with tempfile.TemporaryDirectory() as directory:
            history = pipeline.load_intent_history(Path(directory) / "missing.json")
        self.assertEqual(history["version"], "1.0")
        self.assertEqual(history["published"], [])

    def test_successful_publish_appends_intent_history(self):
        history = {"version": "1.0", "updated_at": None, "published": []}
        article = {"title": "Jeux comme Elden Ring : 10 alternatives"}
        brief = {"primary_keyword": "jeux comme Elden Ring"}
        wp_result = {
            "published": True,
            "wordpress_status": "publish",
            "wordpress_post_id": 123,
            "wordpress_url": "https://gamerquestfr.com/jeux-comme-elden-ring/",
        }
        updated = pipeline.record_published_intent(history, article, brief, wp_result)
        self.assertEqual(len(updated["published"]), 1)
        self.assertEqual(
            updated["published"][0]["intent_key"],
            normalize_search_intent("jeux comme Elden Ring"),
        )
        self.assertEqual(updated["published"][0]["wordpress_post_id"], 123)

    def test_failed_publish_does_not_append_history(self):
        history = {"version": "1.0", "updated_at": None, "published": []}
        updated = pipeline.record_published_intent(
            history,
            {"title": "Jeux comme Elden Ring"},
            {"primary_keyword": "jeux comme Elden Ring"},
            {"published": False, "wordpress_status": "draft"},
        )
        self.assertEqual(updated["published"], [])

    def test_history_collision_is_rejected_before_generation(self):
        topic = {
            "id": "elden-alternatives",
            "topic": "Jeux comme Elden Ring",
            "decision": "WRITE",
            "total_score": 91,
            "seo": {"primary_keyword": "jeux comme Elden Ring"},
        }
        history = {
            "version": "1.0",
            "published": [{"intent_key": normalize_search_intent("jeux comme Elden Ring")}],
        }
        with patch.object(pipeline, "generate_seo_article", side_effect=AssertionError("duplicate reached generation")):
            candidates = select_seo_candidates(
                {"topics": [topic]},
                max_articles=1,
                history=history,
            )
        self.assertEqual(candidates, [])


if __name__ == "__main__":
    unittest.main()
