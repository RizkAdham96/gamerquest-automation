import unittest
from unittest.mock import patch

from social import ai_client, carousel_writer, idea_generator, run


class TestSocialAIRunner(unittest.TestCase):

    @patch("social.idea_generator.generate_ideas")
    def test_build_candidate_ideas_uses_ai_generator(
        self,
        mock_generate_ideas,
    ):
        content = [{"title": "Test gaming article", "source_type": "news"}]
        expected = [{"topic": "Test topic", "format": "breaking_news"}]
        mock_generate_ideas.return_value = expected
        result = run.build_candidate_ideas(content)
        self.assertEqual(result, expected)
        mock_generate_ideas.assert_called_once_with(content)

    def test_extract_text_reads_groq_chat_completion(self):
        response = {"choices": [{"message": {"role": "assistant", "content": "Five original GamerQuest carousel ideas"}}]}
        self.assertEqual(ai_client.extract_text(response), "Five original GamerQuest carousel ideas")

    @patch.dict("os.environ", {"GROQ_API_KEY": "test-key"})
    @patch("social.ai_client.urllib.request.urlopen")
    def test_groq_request_has_user_agent(self, mock_urlopen):
        mock_response = mock_urlopen.return_value.__enter__.return_value
        mock_response.read.return_value = b'{"choices":[{"message":{"content":"ok"}}]}'
        ai_client.call_grok("test prompt")
        request = mock_urlopen.call_args.args[0]
        self.assertEqual(request.get_header("User-agent"), "GamerQuest-Social/1.0")

    def test_prepare_content_limits_ai_input_to_ten_compact_items(self):
        content = [{"title": f"Article {index}", "excerpt": "x" * 2000, "content": "very large article body" * 500, "slug": f"article-{index}", "source_type": "news", "created_at": f"2026-09-{index + 1:02d}T10:00:00+00:00"} for index in range(15)]
        prepared = idea_generator.prepare_content_for_ai(content)
        self.assertEqual(len(prepared), 10)
        self.assertTrue(all("content" not in item for item in prepared))
        self.assertTrue(all(len(item.get("excerpt", "")) <= 500 for item in prepared))

    def test_build_prompt_stays_below_safe_character_budget(self):
        content = [{"title": f"Large article {index}", "excerpt": "x" * 5000, "content": "y" * 50000, "slug": f"large-{index}", "source_type": "news"} for index in range(20)]
        self.assertLessEqual(len(idea_generator.build_prompt(content)), 16000)

    def test_carousel_package_keeps_caption_and_hashtags(self):
        idea = {"topic": "Test topic", "angle": "Test angle", "format": "ranking", "hook": "Test hook", "total_score": 80, "slides": [{"title": f"Slide {index}", "body": "Body"} for index in range(1, 6)], "caption": "A caption that adds context and drives clicks.", "cta": "Full ranking on GamerQuest.fr", "hashtags": ["#GamerQuest", "#GamingNews"]}
        carousel = carousel_writer.build_carousel(idea)
        self.assertEqual(carousel["caption"], "A caption that adds context and drives clicks.")
        self.assertEqual(carousel["hashtags"], ["#GamerQuest", "#GamingNews"])

    @patch("social.idea_generator.call_grok")
    def test_generate_ideas_requests_only_compact_concepts(self, mock_call):
        mock_call.return_value = '[{"topic":"A","angle":"B","format":"ranking","hook":"C","freshness":8,"click_potential":8,"curiosity":8,"shareability":8,"originality":8,"gamerquest_relevance":8}]'
        ideas = idea_generator.generate_ideas([{"title": "Article", "source_type": "news"}])
        self.assertEqual(len(ideas), 1)
        prompt = mock_call.call_args.args[0]
        self.assertNotIn('"slides"', prompt)
        self.assertNotIn('"caption"', prompt)

    @patch("social.idea_generator.call_grok")
    def test_expand_idea_generates_complete_carousel_package(self, mock_call):
        mock_call.return_value = '{"slides":[{"title":"1","body":"a","visual_prompt":"v"},{"title":"2","body":"b","visual_prompt":"v"},{"title":"3","body":"c","visual_prompt":"v"},{"title":"4","body":"d","visual_prompt":"v"},{"title":"5","body":"e","visual_prompt":"v"}],"caption":"Caption","cta":"Read more on GamerQuest.fr","hashtags":["#GamerQuest","#Gaming"]}'
        base = {"topic":"Topic","angle":"Angle","format":"ranking","hook":"Hook","total_score":82}
        result = idea_generator.expand_idea(base, [{"title":"Article","excerpt":"Facts","source_type":"news"}])
        self.assertEqual(result["topic"], "Topic")
        self.assertEqual(len(result["slides"]), 5)
        self.assertEqual(result["caption"], "Caption")
        self.assertEqual(result["total_score"], 82)


if __name__ == "__main__":
    unittest.main()
