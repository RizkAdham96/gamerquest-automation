import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


def load_publish_run():
    spec = importlib.util.find_spec(
        "social.publish_run"
    )

    if spec is None:
        return None

    from social import publish_run

    return publish_run


class TestPublishRun(unittest.TestCase):

    def setUp(self):
        self.publisher = load_publish_run()

    def test_publish_run_module_exists(self):
        self.assertIsNotNone(
            self.publisher,
            (
                "social/publish_run.py "
                "does not exist yet."
            ),
        )

    def test_extract_publish_package(self):
        if self.publisher is None:
            self.fail(
                "social/publish_run.py "
                "does not exist yet."
            )

        social_output = {
            "status": "ready",
            "source_id": "article-123",
            "caption": "Test GamerQuest caption",
            "hashtags": [
                "GamerQuest",
                "Gaming",
            ],
        }

        publish_ready = {
            "source_id": "article-123",
            "image_urls": [
                "https://example.com/slide-1.png",
                "https://example.com/slide-2.png",
                "https://example.com/slide-3.png",
            ],
        }

        package = (
            self.publisher.extract_publish_package(
                social_output,
                publish_ready,
            )
        )

        self.assertEqual(
            package["source_id"],
            "article-123",
        )

        self.assertEqual(
            len(package["image_urls"]),
            3,
        )

        self.assertIn(
            "Test GamerQuest caption",
            package["caption"],
        )

        self.assertIn(
            "#GamerQuest",
            package["caption"],
        )

    def test_rejects_mismatched_source_ids(self):
        if self.publisher is None:
            self.fail(
                "social/publish_run.py "
                "does not exist yet."
            )

        social_output = {
            "status": "ready",
            "source_id": "article-a",
            "caption": "Caption",
            "hashtags": [],
        }

        publish_ready = {
            "source_id": "article-b",
            "image_urls": [
                "https://example.com/1.png",
                "https://example.com/2.png",
                "https://example.com/3.png",
            ],
        }

        with self.assertRaises(
            RuntimeError
        ):
            self.publisher.extract_publish_package(
                social_output,
                publish_ready,
            )

    def test_successful_instagram_is_saved_before_facebook_failure(self):
        if self.publisher is None:
            self.fail(
                "social/publish_run.py "
                "does not exist yet."
            )

        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)

            output_file = (
                directory
                / "social-output.json"
            )

            ready_file = (
                directory
                / "social-publish-ready.json"
            )

            history_file = (
                directory
                / "publish_history.json"
            )

            output_file.write_text(
                json.dumps(
                    {
                        "status": "ready",
                        "source_id": "article-123",
                        "caption": "Test caption",
                        "hashtags": [
                            "GamerQuest"
                        ],
                    }
                ),
                encoding="utf-8",
            )

            ready_file.write_text(
                json.dumps(
                    {
                        "source_id": "article-123",
                        "image_urls": [
                            "https://example.com/1.png",
                            "https://example.com/2.png",
                            "https://example.com/3.png",
                        ],
                    }
                ),
                encoding="utf-8",
            )

            fake_environment = {
                "META_IG_ACCESS_TOKEN":
                    "ig-secret",
                "META_FB_PAGE_ACCESS_TOKEN":
                    "fb-secret",
                "META_IG_USER_ID":
                    "ig-user-123",
                "META_PAGE_ID":
                    "page-123",
            }

            def fake_instagram(**kwargs):
                return {
                    "published": True,
                    "platform": "instagram",
                    "post_id": "ig-post-123",
                }

            def fake_facebook(**kwargs):
                raise RuntimeError(
                    "Facebook test failure"
                )

            with patch.dict(
                os.environ,
                fake_environment,
                clear=False,
            ):
                with patch.object(
                    self.publisher,
                    "publish_instagram_carousel",
                    side_effect=fake_instagram,
                ):
                    with patch.object(
                        self.publisher,
                        "publish_facebook_carousel",
                        side_effect=fake_facebook,
                    ):
                        with self.assertRaises(
                            RuntimeError
                        ):
                            self.publisher.run_publish(
                                output_file=output_file,
                                ready_file=ready_file,
                                history_file=history_file,
                                wait_for_urls=False,
                            )

            history = json.loads(
                history_file.read_text(
                    encoding="utf-8"
                )
            )

            self.assertTrue(
                history[
                    "article-123"
                ][
                    "instagram"
                ][
                    "published"
                ]
            )

            self.assertEqual(
                history[
                    "article-123"
                ][
                    "instagram"
                ][
                    "post_id"
                ],
                "ig-post-123",
            )

            self.assertFalse(
                history[
                    "article-123"
                ][
                    "facebook"
                ][
                    "published"
                ]
            )

    def test_rerun_skips_already_published_instagram(self):
        if self.publisher is None:
            self.fail(
                "social/publish_run.py "
                "does not exist yet."
            )

        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)

            output_file = (
                directory
                / "social-output.json"
            )

            ready_file = (
                directory
                / "social-publish-ready.json"
            )

            history_file = (
                directory
                / "publish_history.json"
            )

            output_file.write_text(
                json.dumps(
                    {
                        "status": "ready",
                        "source_id": "article-123",
                        "caption": "Test caption",
                        "hashtags": [],
                    }
                ),
                encoding="utf-8",
            )

            ready_file.write_text(
                json.dumps(
                    {
                        "source_id": "article-123",
                        "image_urls": [
                            "https://example.com/1.png",
                            "https://example.com/2.png",
                            "https://example.com/3.png",
                        ],
                    }
                ),
                encoding="utf-8",
            )

            history_file.write_text(
                json.dumps(
                    {
                        "article-123": {
                            "instagram": {
                                "published": True,
                                "post_id":
                                    "existing-ig-post",
                            },
                            "facebook": {
                                "published": False,
                                "post_id": "",
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            fake_environment = {
                "META_IG_ACCESS_TOKEN":
                    "ig-secret",
                "META_FB_PAGE_ACCESS_TOKEN":
                    "fb-secret",
                "META_IG_USER_ID":
                    "ig-user-123",
                "META_PAGE_ID":
                    "page-123",
            }

            instagram_calls = []

            def fake_instagram(**kwargs):
                instagram_calls.append(
                    kwargs
                )

                return {
                    "published": True,
                    "post_id": "new-ig-post",
                }

            def fake_facebook(**kwargs):
                return {
                    "published": True,
                    "platform": "facebook",
                    "post_id": "fb-post-123",
                }

            with patch.dict(
                os.environ,
                fake_environment,
                clear=False,
            ):
                with patch.object(
                    self.publisher,
                    "publish_instagram_carousel",
                    side_effect=fake_instagram,
                ):
                    with patch.object(
                        self.publisher,
                        "publish_facebook_carousel",
                        side_effect=fake_facebook,
                    ):
                        result = (
                            self.publisher.run_publish(
                                output_file=output_file,
                                ready_file=ready_file,
                                history_file=history_file,
                                wait_for_urls=False,
                            )
                        )

            self.assertEqual(
                instagram_calls,
                [],
            )

            self.assertEqual(
                result["facebook"]["post_id"],
                "fb-post-123",
            )


if __name__ == "__main__":
    unittest.main()
