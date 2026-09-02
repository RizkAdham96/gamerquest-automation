import unittest
from unittest.mock import patch

from social.run import build_candidate_ideas


class TestSocialAIRunner(unittest.TestCase):

   @patch("social.idea_generator.generate_ideas")
    def test_build_candidate_ideas_uses_ai_generator(
        self,
        mock_generate_ideas,
    ):
        content = [
            {
                "title": "Test gaming article",
                "source_type": "news",
            }
        ]

        expected = [
            {
                "topic": "Test topic",
                "format": "breaking_news",
            }
        ]

        mock_generate_ideas.return_value = expected

        result = build_candidate_ideas(content)

        self.assertEqual(result, expected)
        mock_generate_ideas.assert_called_once_with(content)


if __name__ == "__main__":
    unittest.main()
