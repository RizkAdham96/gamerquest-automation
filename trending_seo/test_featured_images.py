import unittest
from unittest.mock import patch

import pipeline


class FakeResponse:
    def __init__(self, status_code, content=b"", headers=None, payload=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeMediaClient:
    def __init__(self):
        self.posts = []

    def get(self, url, **kwargs):
        return FakeResponse(
            200,
            content=b"real-image-bytes",
            headers={"Content-Type": "image/jpeg"},
        )

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return FakeResponse(201, payload={"id": 456})


class ExplodingPostClient:
    def post(self, *args, **kwargs):
        raise AssertionError("A text-only article must not reach WordPress")


class FakeWordPressClient:
    def __init__(self):
        self.payload = None

    def post(self, url, **kwargs):
        self.payload = kwargs.get("json")
        return FakeResponse(
            201,
            payload={
                "id": 789,
                "status": "publish",
                "link": "https://gamerquestfr.com/witcher-3/",
            },
        )


class TestTrendingSeoFeaturedImages(unittest.TestCase):
    def test_existing_scored_topic_recovers_its_intel_sources(self):
        scored_topic = {
            "id": "witcher-3",
            "topic": "The Witcher 3 Remastered",
        }
        source = {
            "type": "official",
            "url": "https://games.example/witcher-3",
            "title": "Official announcement",
        }
        intel_data = {
            "topics": [{
                "id": "witcher-3",
                "sources": [source],
            }]
        }

        enriched = pipeline.with_intel_sources(scored_topic, intel_data)

        self.assertEqual(enriched["sources"], [source])

    def test_relevant_game_image_wins_over_generic_logo(self):
        html = """
        <html><head>
          <meta property="og:image" content="/images/gamescom-logo.jpg">
        </head><body>
          <img src="/images/witcher-3-remastered-hero.jpg"
               alt="The Witcher 3 Remastered">
        </body></html>
        """

        selected = pipeline.extract_relevant_image_url(
            html,
            "https://games.example/announcement",
            "The Witcher 3 Remastered",
        )

        self.assertEqual(
            selected,
            "https://games.example/images/witcher-3-remastered-hero.jpg",
        )

    def test_hashed_og_image_is_allowed_when_page_is_clearly_about_topic(self):
        html = """
        <html><head>
          <title>The Witcher 3 Remastered — official reveal</title>
          <meta property="og:title" content="The Witcher 3 Remastered">
          <meta property="og:image" content="https://cdn.example/9f31a8b7c4.jpg">
        </head><body>
          <h1>The Witcher 3 Remastered</h1>
        </body></html>
        """

        self.assertEqual(
            pipeline.extract_relevant_image_url(
                html,
                "https://publisher.example/witcher-remastered",
                "The Witcher 3 Remastered",
            ),
            "https://cdn.example/9f31a8b7c4.jpg",
        )

    def test_hashed_og_image_is_rejected_when_page_is_not_about_topic(self):
        html = """
        <html><head>
          <title>Gamescom 2026 homepage</title>
          <meta property="og:image" content="https://cdn.example/9f31a8b7c4.jpg">
        </head><body>
          <h1>Gamescom 2026</h1>
        </body></html>
        """

        self.assertEqual(
            pipeline.extract_relevant_image_url(
                html,
                "https://publisher.example/home",
                "The Witcher 3 Remastered",
            ),
            "",
        )

    def test_generic_image_is_rejected(self):
        html = """
        <meta property="og:image" content="/images/gamescom-logo.jpg">
        <img src="/images/header.jpg" alt="Gamescom">
        """

        self.assertEqual(
            pipeline.extract_relevant_image_url(
                html,
                "https://games.example/announcement",
                "The Witcher 3 Remastered",
            ),
            "",
        )

    def test_image_is_uploaded_to_wordpress_media(self):
        client = FakeMediaClient()

        result = pipeline.upload_featured_image(
            image_url="https://cdn.example/witcher.jpg",
            article_title="The Witcher 3 Remastered",
            wp_config={
                "base_url": "https://gamerquestfr.com",
                "username": "user",
                "application_password": "password",
            },
            client=client,
        )

        self.assertEqual(result["status"], "FEATURED_IMAGE_READY")
        self.assertEqual(result["media_id"], 456)
        self.assertEqual(
            client.posts[0][0],
            "https://gamerquestfr.com/wp-json/wp/v2/media",
        )

    def test_article_without_featured_media_is_blocked(self):
        with patch.object(pipeline, "requests", ExplodingPostClient()):
            result = pipeline.create_wordpress_draft(
                article={
                    "title": "The Witcher 3 Remastered",
                    "content": "<h2>Informations</h2><p>Article.</p>",
                    "meta_description": "Description",
                    "publishable": True,
                },
                wp_config={
                    "base_url": "https://gamerquestfr.com",
                    "username": "user",
                    "application_password": "password",
                },
            )

        self.assertEqual(result["status"], "BLOCKED_FEATURED_IMAGE_REQUIRED")

    def test_wordpress_article_uses_uploaded_media_as_featured_image(self):
        client = FakeWordPressClient()
        with patch.object(pipeline, "requests", client):
            result = pipeline.create_wordpress_draft(
                article={
                    "title": "The Witcher 3 Remastered",
                    "content": "<h2>Informations</h2><p>Article.</p>",
                    "meta_description": "Description",
                    "publishable": True,
                    "featured_media": 456,
                },
                wp_config={
                    "base_url": "https://gamerquestfr.com",
                    "username": "user",
                    "application_password": "password",
                },
            )

        self.assertEqual(result["status"], "WORDPRESS_POST_PUBLISHED")
        self.assertEqual(client.payload["featured_media"], 456)
        self.assertEqual(client.payload["status"], "publish")


if __name__ == "__main__":
    unittest.main()

# Regression trigger: verifies the patched selector on the branch.
