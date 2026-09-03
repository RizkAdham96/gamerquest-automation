import unittest
from unittest.mock import patch

from social import ai_client, run


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

        result = run.build_candidate_ideas(content)

        self.assertEqual(result, expected)
        mock_generate_ideas.assert_called_once_with(content)

    def test_extract_text_reads_groq_chat_completion(self):
        response = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "Five original GamerQuest carousel ideas",
                    }
                }
            ]
        }

        result = ai_client.extract_text(response)

        self.assertEqual(
            result,
            "Five original GamerQuest carousel ideas",
        )

    @patch.dict("os.environ", {"GROQ_API_KEY": "test-key"})
    @patch("social.ai_client.urllib.request.urlopen")
    def test_groq_request_has_user_agent(self, mock_urlopen):
        mock_response = mock_urlopen.return_value.__enter__.return_value
        mock_response.read.return_value = (
            b'{"choices":[{"message":{"content":"ok"}}]}'
        )

        ai_client.call_grok("test prompt")

        request = mock_urlopen.call_args.args[0]
        self.assertEqual(
            request.get_header("User-agent"),
            "GamerQuest-Social/1.0",
        )


if __name__ == "__main__":
    unittest.main()
