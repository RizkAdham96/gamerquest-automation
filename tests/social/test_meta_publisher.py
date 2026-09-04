import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


def load_meta_publisher():
    spec = importlib.util.find_spec(
        "social.meta_publisher"
    )

    if spec is None:
        return None

    from social import meta_publisher

    return meta_publisher


class FakeResponse:

    def __init__(
        self,
        payload,
        status_code=200,
    ):
        self.payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(
                f"HTTP {self.status_code}: {self.text}"
            )


class FakeRequests:

    def __init__(self):
        self.calls = []
        self.counter = 0

    def post(
        self,
        url,
        data=None,
        params=None,
        timeout=None,
    ):
        self.calls.append(
            {
                "method": "POST",
                "url": url,
                "data": data,
                "params": params,
                "timeout": timeout,
            }
        )

        self.counter += 1

        return FakeResponse(
            {
                "id": f"fake-{self.counter}"
            }
        )

    def get(
        self,
        url,
        params=None,
        timeout=None,
    ):
        self.calls.append(
            {
                "method": "GET",
                "url": url,
                "params": params,
                "timeout": timeout,
            }
        )

        return FakeResponse(
            {
                "status_code": "FINISHED"
            }
        )


class TestMetaPublisher(unittest.TestCase):

    def setUp(self):
        self.publisher = (
            load_meta_publisher()
        )

    def test_meta_publisher_module_exists(self):
        self.assertIsNotNone(
            self.publisher,
            (
                "social/meta_publisher.py "
                "does not exist yet."
            ),
        )

    def test_build_raw_github_urls(self):
        paths = [
            "social-published/test/slide-1.png",
            "social-published/test/slide-2.png",
            "social-published/test/slide-3.png",
        ]

        result = (
            self.publisher.build_raw_github_urls(
                image_paths=paths,
                repository=(
                    "RizkAdham96/"
                    "gamerquest-automation"
                ),
                branch="main",
            )
        )

        self.assertEqual(
            len(result),
            3,
        )

        self.assertEqual(
            result[0],
            (
                "https://raw.githubusercontent.com/"
                "RizkAdham96/"
                "gamerquest-automation/"
                "main/"
                "social-published/test/"
                "slide-1.png"
            ),
        )

    def test_publish_history_defaults_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            history_file = (
                Path(directory)
                / "publish_history.json"
            )

            history = (
                self.publisher.load_publish_history(
                    history_file
                )
            )

            self.assertEqual(
                history,
                {},
            )

    def test_publish_history_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            history_file = (
                Path(directory)
                / "publish_history.json"
            )

            expected = {
                "source-123": {
                    "instagram": {
                        "published": True,
                        "post_id": "ig-1",
                    },
                    "facebook": {
                        "published": False,
                        "post_id": "",
                    },
                }
            }

            self.publisher.save_publish_history(
                expected,
                history_file,
            )

            loaded = (
                self.publisher.load_publish_history(
                    history_file
                )
            )

            self.assertEqual(
                loaded,
                expected,
            )

    def test_pending_platforms_returns_both_for_new_source(self):
        result = (
            self.publisher.pending_platforms(
                source_id="source-123",
                history={},
            )
        )

        self.assertEqual(
            result,
            [
                "instagram",
                "facebook",
            ],
        )

    def test_pending_platforms_retries_only_failed_platform(self):
        history = {
            "source-123": {
                "instagram": {
                    "published": True,
                    "post_id": "ig-123",
                },
                "facebook": {
                    "published": False,
                    "post_id": "",
                },
            }
        }

        result = (
            self.publisher.pending_platforms(
                source_id="source-123",
                history=history,
            )
        )

        self.assertEqual(
            result,
            [
                "facebook",
            ],
        )

    def test_pending_platforms_returns_empty_when_both_done(self):
        history = {
            "source-123": {
                "instagram": {
                    "published": True,
                    "post_id": "ig-123",
                },
                "facebook": {
                    "published": True,
                    "post_id": "fb-123",
                },
            }
        }

        result = (
            self.publisher.pending_platforms(
                source_id="source-123",
                history=history,
            )
        )

        self.assertEqual(
            result,
            [],
        )

    def test_caption_combines_caption_and_hashtags(self):
        result = (
            self.publisher.build_caption(
                caption=(
                    "Le nouveau trailer "
                    "vient de tomber."
                ),
                hashtags=[
                    "#GamerQuest",
                    "#Gaming",
                    "#FFVII",
                ],
            )
        )

        self.assertEqual(
            result,
            (
                "Le nouveau trailer "
                "vient de tomber.\n\n"
                "#GamerQuest "
                "#Gaming "
                "#FFVII"
            ),
        )

    def test_instagram_uses_instagram_graph_host(self):
        fake_requests = FakeRequests()

        self.publisher.publish_instagram_carousel(
            image_urls=[
                "https://example.com/1.png",
                "https://example.com/2.png",
                "https://example.com/3.png",
            ],
            caption="Test caption",
            ig_user_id="123456",
            access_token="secret-token",
            requests_module=fake_requests,
        )

        for call in fake_requests.calls:
            self.assertTrue(
                call["url"].startswith(
                    "https://graph.instagram.com/"
                ),
                call["url"],
            )

    def test_facebook_uses_facebook_graph_host(self):
        fake_requests = FakeRequests()

        self.publisher.publish_facebook_carousel(
            image_urls=[
                "https://example.com/1.png",
                "https://example.com/2.png",
                "https://example.com/3.png",
            ],
            caption="Test caption",
            page_id="987654",
            access_token="secret-token",
            requests_module=fake_requests,
        )

        for call in fake_requests.calls:
            self.assertTrue(
                call["url"].startswith(
                    "https://graph.facebook.com/"
                ),
                call["url"],
            )

    def test_instagram_creates_three_children_then_carousel(self):
        fake_requests = FakeRequests()

        result = (
            self.publisher.publish_instagram_carousel(
                image_urls=[
                    "https://example.com/1.png",
                    "https://example.com/2.png",
                    "https://example.com/3.png",
                ],
                caption="Test caption",
                ig_user_id="123456",
                access_token="secret-token",
                requests_module=fake_requests,
            )
        )

        self.assertTrue(
            result["published"]
        )

        self.assertEqual(
            len(fake_requests.calls),
            5,
        )

        for call in fake_requests.calls[:3]:
            self.assertIn(
                "/123456/media",
                call["url"],
            )

            self.assertTrue(
                call["data"]["is_carousel_item"]
            )

        parent_call = (
            fake_requests.calls[3]
        )

        self.assertEqual(
            parent_call["data"][
                "media_type"
            ],
            "CAROUSEL",
        )

        publish_call = (
            fake_requests.calls[4]
        )

        self.assertIn(
            "/123456/media_publish",
            publish_call["url"],
        )

    def test_facebook_uploads_three_unpublished_photos_then_post(self):
        fake_requests = FakeRequests()

        result = (
            self.publisher.publish_facebook_carousel(
                image_urls=[
                    "https://example.com/1.png",
                    "https://example.com/2.png",
                    "https://example.com/3.png",
                ],
                caption="Test caption",
                page_id="987654",
                access_token="secret-token",
                requests_module=fake_requests,
            )
        )

        self.assertTrue(
            result["published"]
        )

        self.assertEqual(
            len(fake_requests.calls),
            4,
        )

        for call in fake_requests.calls[:3]:
            self.assertIn(
                "/987654/photos",
                call["url"],
            )

            self.assertFalse(
                call["data"]["published"]
            )

        final_call = (
            fake_requests.calls[3]
        )

        self.assertIn(
            "/987654/feed",
            final_call["url"],
        )

        self.assertEqual(
            final_call["data"]["message"],
            "Test caption",
        )


if __name__ == "__main__":
    unittest.main()
