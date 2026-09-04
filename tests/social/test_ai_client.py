import unittest

from social.ai_client import _rate_limit_wait_seconds


class TestGroqRateLimit(unittest.TestCase):

    def test_parses_seconds_from_groq_rate_limit(self):
        error_body = (
            "Rate limit reached. "
            "Please try again in 8.29s."
        )

        wait = _rate_limit_wait_seconds(error_body)

        self.assertAlmostEqual(wait, 9.29, places=2)

    def test_parses_minutes_and_seconds_from_groq_rate_limit(self):
        error_body = (
            "Rate limit reached. "
            "Please try again in 8m29.76s."
        )

        wait = _rate_limit_wait_seconds(error_body)

        # 8 minutes + 29.76 seconds + 1 second safety buffer
        self.assertAlmostEqual(wait, 510.76, places=2)

    def test_uses_fallback_when_groq_does_not_provide_wait_time(self):
        error_body = "Rate limit exceeded."

        wait = _rate_limit_wait_seconds(error_body)

        self.assertEqual(wait, 5.0)


if __name__ == "__main__":
    unittest.main()
