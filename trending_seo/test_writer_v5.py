import unittest

from writer import (
    build_publish_request,
    run_wordpress_publish,
    finalize_publish_result,
)


class FakeResponse:
    def __init__(
        self,
        status_code=201,
        payload=None,
    ):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


class FakeWordPressClient:
    def __init__(
        self,
        status_code=201,
        payload=None,
    ):
        self.status_code = status_code
        self.payload = payload or {
            "id": 123,
            "link": (
                "https://gamerquestfr.com/"
                "test-article/"
            ),
        }

        self.calls = 0
        self.last_url = None
        self.last_kwargs = None

    def post(
        self,
        url,
        **kwargs,
    ):
        self.calls += 1
        self.last_url = url
        self.last_kwargs = kwargs

        return FakeResponse(
            status_code=self.status_code,
            payload=self.payload,
        )


class ExplodingWordPressClient:
    def __init__(self):
        self.calls = 0

    def post(
        self,
        url,
        **kwargs,
    ):
        self.calls += 1

        raise RuntimeError(
            "WordPress unavailable"
        )


class TestWriterV5PublishingGate(
    unittest.TestCase
):

    # ======================================================
    # FINAL PRODUCTION GATE
    # ======================================================

    def test_non_validated_draft_is_blocked(self):
        draft = {
            "status": (
                "DRAFT_PENDING_VALIDATION"
            ),
            "title": "Test Game",
            "content": (
                "Confirmed information."
            ),
            "meta_description": (
                "Confirmed information."
            ),
            "publishable": False,
            "published": False,
        }

        validation = {
            "status": "VALIDATION_PASSED",
            "unsupported_claims": [],
        }

        result = build_publish_request(
            draft=draft,
            validation=validation,
            wordpress_config={
                "base_url": (
                    "https://gamerquestfr.com"
                ),
                "username": "test-user",
                "application_password": (
                    "test-password"
                ),
            },
        )

        self.assertEqual(
            result["status"],
            "BLOCKED_NOT_VALIDATED_DRAFT",
        )

        self.assertFalse(
            result["should_publish"]
        )


    def test_publishable_false_is_blocked(self):
        draft = {
            "status": "VALIDATED_DRAFT",
            "title": "Test Game",
            "content": (
                "Confirmed information."
            ),
            "meta_description": (
                "Confirmed information."
            ),
            "publishable": False,
            "published": False,
        }

        validation = {
            "status": "VALIDATION_PASSED",
            "unsupported_claims": [],
        }

        result = build_publish_request(
            draft=draft,
            validation=validation,
            wordpress_config={
                "base_url": (
                    "https://gamerquestfr.com"
                ),
                "username": "test-user",
                "application_password": (
                    "test-password"
                ),
            },
        )

        self.assertEqual(
            result["status"],
            "BLOCKED_NOT_PUBLISHABLE",
        )

        self.assertFalse(
            result["should_publish"]
        )


    def test_already_published_draft_is_blocked(self):
        draft = {
            "status": "VALIDATED_DRAFT",
            "title": "Test Game",
            "content": (
                "Confirmed information."
            ),
            "meta_description": (
                "Confirmed information."
            ),
            "publishable": True,
            "published": True,
        }

        validation = {
            "status": "VALIDATION_PASSED",
            "unsupported_claims": [],
        }

        result = build_publish_request(
            draft=draft,
            validation=validation,
            wordpress_config={
                "base_url": (
                    "https://gamerquestfr.com"
                ),
                "username": "test-user",
                "application_password": (
                    "test-password"
                ),
            },
        )

        self.assertEqual(
            result["status"],
            "BLOCKED_ALREADY_PUBLISHED",
        )

        self.assertFalse(
            result["should_publish"]
        )


    def test_failed_validation_is_blocked(self):
        draft = {
            "status": "VALIDATED_DRAFT",
            "title": "Test Game",
            "content": (
                "Confirmed information."
            ),
            "meta_description": (
                "Confirmed information."
            ),
            "publishable": True,
            "published": False,
        }

        validation = {
            "status": (
                "BLOCKED_UNSUPPORTED_CLAIMS"
            ),
            "unsupported_claims": [
                "Unsupported release date."
            ],
        }

        result = build_publish_request(
            draft=draft,
            validation=validation,
            wordpress_config={
                "base_url": (
                    "https://gamerquestfr.com"
                ),
                "username": "test-user",
                "application_password": (
                    "test-password"
                ),
            },
        )

        self.assertEqual(
            result["status"],
            "BLOCKED_VALIDATION_NOT_PASSED",
        )

        self.assertFalse(
            result["should_publish"]
        )


    def test_missing_wordpress_config_is_blocked(self):
        draft = {
            "status": "VALIDATED_DRAFT",
            "title": "Test Game",
            "content": (
                "Confirmed information."
            ),
            "meta_description": (
                "Confirmed information."
            ),
            "publishable": True,
            "published": False,
        }

        validation = {
            "status": "VALIDATION_PASSED",
            "unsupported_claims": [],
        }

        result = build_publish_request(
            draft=draft,
            validation=validation,
            wordpress_config={},
        )

        self.assertEqual(
            result["status"],
            "BLOCKED_WORDPRESS_CONFIG",
        )

        self.assertFalse(
            result["should_publish"]
        )


    def test_valid_draft_creates_publish_request(self):
        draft = {
            "status": "VALIDATED_DRAFT",
            "title": (
                "Test Game : annonce officielle"
            ),
            "content": (
                "Le jeu a été officiellement "
                "annoncé."
            ),
            "meta_description": (
                "Informations confirmées "
                "sur Test Game."
            ),
            "publishable": True,
            "published": False,
        }

        validation = {
            "status": "VALIDATION_PASSED",
            "unsupported_claims": [],
        }

        result = build_publish_request(
            draft=draft,
            validation=validation,
            wordpress_config={
                "base_url": (
                    "https://gamerquestfr.com/"
                ),
                "username": "test-user",
                "application_password": (
                    "test-password"
                ),
            },
        )

        self.assertEqual(
            result["status"],
            "READY_FOR_WORDPRESS",
        )

        self.assertTrue(
            result["should_publish"]
        )

        self.assertFalse(
            result["published"]
        )

        self.assertEqual(
            result["payload"]["status"],
            "publish",
        )


    # ======================================================
    # WORDPRESS BRIDGE
    # ======================================================

    def test_blocked_request_never_calls_wordpress(self):
        client = FakeWordPressClient()

        result = run_wordpress_publish(
            publish_request={
                "status": (
                    "BLOCKED_NOT_PUBLISHABLE"
                ),
                "should_publish": False,
            },
            client=client,
        )

        self.assertEqual(
            client.calls,
            0,
        )

        self.assertFalse(
            result["published"]
        )


    def test_valid_request_calls_wordpress_once(self):
        client = FakeWordPressClient()

        request = {
            "status": "READY_FOR_WORDPRESS",
            "should_publish": True,
            "endpoint": (
                "https://gamerquestfr.com/"
                "wp-json/wp/v2/posts"
            ),
            "username": "test-user",
            "application_password": (
                "test-password"
            ),
            "payload": {
                "title": "Test Game",
                "content": (
                    "Confirmed information."
                ),
                "excerpt": (
                    "Confirmed information."
                ),
                "status": "publish",
            },
            "published": False,
        }

        result = run_wordpress_publish(
            publish_request=request,
            client=client,
        )

        self.assertEqual(
            client.calls,
            1,
        )

        self.assertEqual(
            result["status"],
            "WORDPRESS_PUBLISH_SUCCESS",
        )

        self.assertTrue(
            result["published"]
        )


    def test_wordpress_success_requires_post_id(self):
        client = FakeWordPressClient(
            status_code=201,
            payload={
                "link": (
                    "https://gamerquestfr.com/"
                    "test/"
                )
            },
        )

        request = {
            "status": "READY_FOR_WORDPRESS",
            "should_publish": True,
            "endpoint": (
                "https://gamerquestfr.com/"
                "wp-json/wp/v2/posts"
            ),
            "username": "test-user",
            "application_password": (
                "test-password"
            ),
            "payload": {
                "title": "Test Game",
                "content": (
                    "Confirmed information."
                ),
                "status": "publish",
            },
        }

        result = run_wordpress_publish(
            publish_request=request,
            client=client,
        )

        self.assertEqual(
            result["status"],
            "BLOCKED_INVALID_WORDPRESS_RESPONSE",
        )

        self.assertFalse(
            result["published"]
        )


    def test_wordpress_http_error_fails_closed(self):
        client = FakeWordPressClient(
            status_code=500,
            payload={
                "message": "Server error"
            },
        )

        request = {
            "status": "READY_FOR_WORDPRESS",
            "should_publish": True,
            "endpoint": (
                "https://gamerquestfr.com/"
                "wp-json/wp/v2/posts"
            ),
            "username": "test-user",
            "application_password": (
                "test-password"
            ),
            "payload": {
                "title": "Test Game",
                "content": (
                    "Confirmed information."
                ),
                "status": "publish",
            },
        }

        result = run_wordpress_publish(
            publish_request=request,
            client=client,
        )

        self.assertEqual(
            result["status"],
            "BLOCKED_WORDPRESS_PUBLISH_ERROR",
        )

        self.assertFalse(
            result["published"]
        )


    def test_wordpress_exception_fails_closed(self):
        client = ExplodingWordPressClient()

        request = {
            "status": "READY_FOR_WORDPRESS",
            "should_publish": True,
            "endpoint": (
                "https://gamerquestfr.com/"
                "wp-json/wp/v2/posts"
            ),
            "username": "test-user",
            "application_password": (
                "test-password"
            ),
            "payload": {
                "title": "Test Game",
                "content": (
                    "Confirmed information."
                ),
                "status": "publish",
            },
        }

        result = run_wordpress_publish(
            publish_request=request,
            client=client,
        )

        self.assertEqual(
            result["status"],
            "BLOCKED_WORDPRESS_UNAVAILABLE",
        )

        self.assertFalse(
            result["published"]
        )


    # ======================================================
    # FINAL RESULT
    # ======================================================

    def test_successful_publish_marks_article_published(self):
        draft = {
            "status": "VALIDATED_DRAFT",
            "title": "Test Game",
            "content": (
                "Confirmed information."
            ),
            "publishable": True,
            "published": False,
        }

        publish_result = {
            "status": (
                "WORDPRESS_PUBLISH_SUCCESS"
            ),
            "published": True,
            "wordpress_post_id": 123,
            "wordpress_url": (
                "https://gamerquestfr.com/"
                "test-game/"
            ),
        }

        result = finalize_publish_result(
            draft=draft,
            publish_result=publish_result,
        )

        self.assertEqual(
            result["status"],
            "PUBLISHED",
        )

        self.assertTrue(
            result["published"]
        )

        self.assertEqual(
            result["wordpress_post_id"],
            123,
        )


    def test_failed_publish_never_marks_article_published(self):
        draft = {
            "status": "VALIDATED_DRAFT",
            "title": "Test Game",
            "content": (
                "Confirmed information."
            ),
            "publishable": True,
            "published": False,
        }

        publish_result = {
            "status": (
                "BLOCKED_WORDPRESS_PUBLISH_ERROR"
            ),
            "published": False,
        }

        result = finalize_publish_result(
            draft=draft,
            publish_result=publish_result,
        )

        self.assertFalse(
            result["published"]
        )


    def test_fake_publish_result_cannot_bypass_gate(self):
        draft = {
            "status": (
                "DRAFT_PENDING_VALIDATION"
            ),
            "title": "Test Game",
            "content": (
                "Unvalidated information."
            ),
            "publishable": False,
            "published": False,
        }

        publish_result = {
            "status": (
                "WORDPRESS_PUBLISH_SUCCESS"
            ),
            "published": True,
            "wordpress_post_id": 999,
        }

        result = finalize_publish_result(
            draft=draft,
            publish_result=publish_result,
        )

        self.assertEqual(
            result["status"],
            "BLOCKED_NOT_VALIDATED_DRAFT",
        )

        self.assertFalse(
            result["published"]
        )


if __name__ == "__main__":
    unittest.main()
