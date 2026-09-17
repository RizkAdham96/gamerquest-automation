import unittest

from social.run_fresh import filter_already_published, filter_renderable_sources


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

    def test_skips_fresh_source_without_three_images_and_uses_next(self):
        content = [
            {"source_id": "bad-images", "title": "Story with one image"},
            {"source_id": "good-images", "title": "Story with three images"},
        ]

        def resolver(source_id, content_items=None):
            if source_id == "bad-images":
                raise RuntimeError("three unique relevant images")
            return ["one.jpg", "two.jpg", "three.jpg"]

        result = filter_renderable_sources(content, image_resolver=resolver)

        self.assertEqual([item["source_id"] for item in result], ["good-images"])


if __name__ == "__main__":
    unittest.main()
