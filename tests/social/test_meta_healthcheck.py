import unittest

from social import meta_healthcheck


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {"id": "123"}

    def json(self):
        return self._payload


class FakeRequests:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        return self.responses.pop(0)


class TestMetaHealthcheck(unittest.TestCase):
    def test_checks_instagram_and_facebook_ids(self):
        fake = FakeRequests([FakeResponse(), FakeResponse()])
        result = meta_healthcheck.check_meta_connection(
            token="token",
            ig_user_id="ig-123",
            page_id="page-123",
            requests_module=fake,
            graph_version="v26.0",
        )
        self.assertTrue(result["ok"])
        self.assertEqual(len(fake.calls), 2)

    def test_rejects_expired_or_invalid_token(self):
        fake = FakeRequests([
            FakeResponse(400, {"error": {"message": "Invalid OAuth access token", "code": 190}})
        ])
        with self.assertRaises(RuntimeError):
            meta_healthcheck.check_meta_connection(
                token="bad",
                ig_user_id="ig-123",
                page_id="page-123",
                requests_module=fake,
                graph_version="v26.0",
            )


if __name__ == "__main__":
    unittest.main()
