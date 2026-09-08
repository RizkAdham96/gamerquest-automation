import unittest
from pathlib import Path

import pipeline


class TestSeoPipelinePublishMode(unittest.TestCase):

    def workflow_text(self):
        workflow_path = (
            Path(__file__).resolve().parents[1]
            / ".github"
            / "workflows"
            / "run-trending-seo-pipeline.yml"
        )
        return workflow_path.read_text(encoding="utf-8")

    def test_seo_pipeline_is_configured_for_public_publish(self):
        self.assertEqual(pipeline.WORDPRESS_STATUS, "publish")

    def test_workflow_does_not_force_legacy_pipeline_to_draft(self):
        workflow = self.workflow_text()
        self.assertNotIn('pipeline.WORDPRESS_STATUS = "draft"', workflow)
        self.assertIn("python trending_seo/pipeline.py", workflow)

    def test_workflow_runs_full_evergreen_regression_suite(self):
        workflow = self.workflow_text()
        required_tests = (
            "test_scorer.py",
            "test_seo_engine.py",
            "test_researcher.py",
            "test_evergreen_research.py",
            "test_writer.py",
            "test_featured_images.py",
            "test_evergreen_pipeline.py",
            "test_pipeline_research_gate.py",
            "test_pipeline_publish_mode.py",
        )
        for test_name in required_tests:
            self.assertIn(test_name, workflow)

    def test_workflow_persists_intent_history(self):
        workflow = self.workflow_text()
        self.assertIn("trending_seo/seo_intent_history.json", workflow)


if __name__ == "__main__":
    unittest.main()
