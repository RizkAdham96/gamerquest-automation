import unittest

from social.run_fresh import filter_already_published


class TestFreshSocialSelection(unittest.TestCase):
    def test_excludes_sources_already_published_to_instagram(self):
        content = [
            {"source_id": "already-posted", "title": "Old story"},
            {"source_id": "fresh-story", "title": "Fresh story"},
        ]
        publish_history = {
            "already-posted": {
                "instagram": {"published": True, "post_id": "ig-123"},
                "facebook": {"published": True, "post_id": "fb-123"},
            }
        }

        result = filter_already_published(content, publish_history)

        self.assertEqual([item["source_id"] for item in result], ["fresh-story"])

    def test_keeps_source_when_previous_instagram_publish_failed(self):
        content = [{"source_id": "retry-me", "title": "Retry story"}]
        publish_history = {
            "retry-me": {
                "instagram": {"published": False, "post_id": ""}
            }
        }

        result = filter_already_published(content, publish_history)

        self.assertEqual([item["source_id"] for item in result], ["retry-me"])


if __name__ == "__main__":
    unittest.main()
