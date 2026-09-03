import io
import unittest
import urllib.error
from unittest.mock import patch
from social import ai_client, carousel_writer, idea_generator, run

class TestSocialAIRunner(unittest.TestCase):
    @patch("social.idea_generator.generate_ideas")
    def test_build_candidate_ideas_uses_ai_generator(self,mock_generate_ideas):
        content=[{"title":"Test gaming article","source_type":"news"}]; expected=[{"topic":"Test topic","format":"breaking_news"}]
        mock_generate_ideas.return_value=expected
        self.assertEqual(run.build_candidate_ideas(content),expected); mock_generate_ideas.assert_called_once_with(content)

    def test_extract_text_reads_groq_chat_completion(self):
        self.assertEqual(ai_client.extract_text({"choices":[{"message":{"role":"assistant","content":"Three original GamerQuest carousel ideas"}}]}),"Three original GamerQuest carousel ideas")

    @patch.dict("os.environ",{"GROQ_API_KEY":"test-key"})
    @patch("social.ai_client.urllib.request.urlopen")
    def test_groq_request_has_user_agent(self,mock_urlopen):
        mock_response=mock_urlopen.return_value.__enter__.return_value; mock_response.read.return_value=b'{"choices":[{"message":{"content":"ok"}}]}'
        ai_client.call_grok("test prompt"); request=mock_urlopen.call_args.args[0]
        self.assertEqual(request.get_header("User-agent"),"GamerQuest-Social/1.0")

    @patch.dict("os.environ",{"GROQ_API_KEY":"test-key"})
    @patch("social.ai_client.time.sleep")
    @patch("social.ai_client.urllib.request.urlopen")
    def test_groq_429_waits_and_retries_once(self,mock_urlopen,mock_sleep):
        body=b'{"error":{"message":"Rate limit reached. Please try again in 3.6525s.","type":"tokens","code":"rate_limit_exceeded"}}'
        error=urllib.error.HTTPError(ai_client.GROQ_API_URL,429,"Too Many Requests",{},io.BytesIO(body))
        success=unittest.mock.MagicMock(); success.__enter__.return_value.read.return_value=b'{"choices":[{"message":{"content":"recovered"}}]}'
        mock_urlopen.side_effect=[error,success]
        self.assertEqual(ai_client.call_grok("test prompt"),"recovered"); self.assertEqual(mock_urlopen.call_count,2); mock_sleep.assert_called_once(); self.assertGreaterEqual(mock_sleep.call_args.args[0],3.6525)

    @patch("social.run.time.sleep")
    @patch("social.run.idea_generator.verify_carousel")
    @patch("social.run.idea_generator.expand_idea")
    @patch("social.run.choose_best_idea")
    @patch("social.run.build_candidate_ideas")
    @patch("social.run.get_all_content")
    def test_run_paces_fact_check_after_expansion(self,mock_content,mock_candidates,mock_choose,mock_expand,mock_verify,mock_sleep):
        content=[{"title":"News","source_type":"news"}]; idea={"topic":"News","total_score":90}
        mock_content.return_value=content; mock_candidates.return_value=[idea]; mock_choose.return_value=idea
        mock_expand.return_value={**idea,"slides":[{"title":str(i),"body":"Body"} for i in range(5)],"caption":"Caption","cta":"CTA","hashtags":["#Gaming"]}
        mock_verify.return_value={"valid":True,"unsupported_claims":[],"reason":""}
        with patch("social.run.build_carousel",return_value={"slides":mock_expand.return_value["slides"],"caption":"Caption","cta":"CTA","hashtags":["#Gaming"]}), patch("social.run.save_output"):
            run.run()
        mock_sleep.assert_any_call(run.GROQ_PACING_SECONDS)
        self.assertGreaterEqual(run.GROQ_PACING_SECONDS,20)

    def test_prepare_content_limits_ai_input_to_ten_compact_items(self):
        content=[{"title":f"Article {i}","excerpt":"x"*2000,"content":"body"*500,"slug":f"article-{i}","source_type":"news","created_at":f"2026-09-{i+1:02d}T10:00:00+00:00"} for i in range(15)]
        prepared=idea_generator.prepare_content_for_ai(content)
        self.assertEqual(len(prepared),10); self.assertTrue(all("content" not in x for x in prepared)); self.assertTrue(all(len(x.get("excerpt",""))<=500 for x in prepared))

    def test_build_prompt_stays_below_safe_character_budget(self):
        content=[{"title":f"Large {i}","excerpt":"x"*5000,"content":"y"*50000,"slug":f"large-{i}","source_type":"news"} for i in range(20)]
        self.assertLessEqual(len(idea_generator.build_prompt(content)),16000)

    def test_carousel_package_keeps_caption_and_hashtags(self):
        idea={"topic":"Test","angle":"Angle","format":"ranking","hook":"Hook","total_score":80,"slides":[{"title":str(i),"body":"Body"} for i in range(5)],"caption":"Caption","cta":"Full ranking on GamerQuest.fr","hashtags":["#GamerQuest","#GamingNews"]}
        carousel=carousel_writer.build_carousel(idea); self.assertEqual(carousel["caption"],"Caption"); self.assertEqual(carousel["hashtags"],["#GamerQuest","#GamingNews"])

    @patch("social.idea_generator.call_grok")
    def test_generate_ideas_limits_concepts_to_three(self,mock_call):
        mock_call.return_value='[{"topic":"A"},{"topic":"B"},{"topic":"C"},{"topic":"D"},{"topic":"E"}]'
        ideas=idea_generator.generate_ideas([{"title":"Article","source_type":"news"}]); self.assertEqual(len(ideas),3); self.assertIn("exactly 3",mock_call.call_args.args[0].lower())

    @patch("social.idea_generator.call_grok")
    def test_expand_idea_generates_complete_carousel_package(self,mock_call):
        mock_call.return_value='{"slides":[{"title":"1","body":"a","visual_prompt":"v"},{"title":"2","body":"b","visual_prompt":"v"},{"title":"3","body":"c","visual_prompt":"v"},{"title":"4","body":"d","visual_prompt":"v"},{"title":"5","body":"e","visual_prompt":"v"}],"caption":"Caption","cta":"Read more on GamerQuest.fr","hashtags":["#GamerQuest","#Gaming"]}'
        result=idea_generator.expand_idea({"topic":"Topic","angle":"Angle","format":"ranking","hook":"Hook","total_score":82},[{"title":"Article","excerpt":"Facts","source_type":"news"}]); self.assertEqual(len(result["slides"]),5); self.assertEqual(result["total_score"],82)

    @patch("social.idea_generator.call_grok")
    def test_verify_carousel_rejects_unsupported_claims(self,mock_call):
        mock_call.return_value='{"valid":false,"unsupported_claims":["cross-platform multiplayer"],"reason":"unsupported"}'
        result=idea_generator.verify_carousel({"topic":"Game","slides":[]},[{"title":"Game","excerpt":"Solo","source_type":"news"}]); self.assertFalse(result["valid"]); self.assertIn("cross-platform multiplayer",result["unsupported_claims"])

    @patch("social.idea_generator.call_grok")
    def test_repair_carousel_changes_only_package_fields(self,mock_call):
        mock_call.return_value='{"slides":[{"title":"1","body":"Supported fact","visual_prompt":"v"}],"caption":"Supported caption","cta":"Read GamerQuest.fr","hashtags":["#GamerQuest"]}'
        original={"topic":"Game","angle":"Deal","format":"deal","hook":"Free now","total_score":80.5,"slides":[{"title":"1","body":"Unsupported claim"}],"caption":"Wrong","cta":"Read","hashtags":["#Gaming"]}
        fixed=idea_generator.repair_carousel(original,[{"title":"Game","excerpt":"Supported fact","source_type":"deal"}],["Unsupported claim"]); self.assertEqual(fixed["topic"],"Game"); self.assertEqual(fixed["total_score"],80.5); self.assertEqual(fixed["slides"][0]["body"],"Supported fact")

if __name__=="__main__": unittest.main()
