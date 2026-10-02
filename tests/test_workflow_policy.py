from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def workflow(name: str) -> str:
    path = WORKFLOWS / name
    if not path.exists():
        raise AssertionError(f"Missing workflow: {name}")
    return path.read_text(encoding="utf-8")


class BalancedAutomationPolicyTests(unittest.TestCase):
    def assert_cron(self, name: str, cron: str) -> None:
        text = workflow(name)
        self.assertIn(f'- cron: "{cron}"', text, name)

    def assert_no_push_trigger(self, name: str) -> None:
        text = workflow(name)
        header = text.split("permissions:", 1)[0]
        self.assertNotRegex(header, r"(?m)^\s{2}push:\s*$", name)

    def assert_no_regression_suite(self, name: str) -> None:
        text = workflow(name)
        self.assertNotIn("python -m pytest", text, name)
        self.assertNotIn("python -m unittest", text, name)
        self.assertNotRegex(text, r"python\s+tests/.+test_", name)

    def test_option_b_schedules(self):
        self.assert_cron("gamerquest.yml", "27 */6 * * *")
        self.assert_cron("run-trending-seo-pipeline.yml", "43 2 * * *")
        self.assert_cron("test-deals.yml", "37 */4 * * *")
        self.assert_cron("reviews.yml", "27 5 * * *")
        self.assert_cron("content-health.yml", "43 */6 * * *")
        self.assert_cron("acquisition-shadow.yml", "17 4 * * *")
        self.assert_cron("social-test.yml", "30 18 * * 0,2,5")
        self.assert_cron("social-publish-recovery.yml", "15 19 * * 0,2,5")

    def test_production_workflows_are_not_push_publishers(self):
        for name in (
            "gamerquest.yml",
            "run-trending-seo-pipeline.yml",
            "test-deals.yml",
            "reviews.yml",
            "content-health.yml",
            "acquisition-shadow.yml",
            "social-test.yml",
            "social-publish-recovery.yml",
        ):
            with self.subTest(workflow=name):
                self.assert_no_push_trigger(name)

    def test_regression_suites_are_not_repeated_in_production(self):
        for name in (
            "gamerquest.yml",
            "run-trending-seo-pipeline.yml",
            "test-deals.yml",
            "reviews.yml",
            "acquisition-shadow.yml",
            "social-test.yml",
            "social-publish-recovery.yml",
        ):
            with self.subTest(workflow=name):
                self.assert_no_regression_suite(name)

    def test_deals_production_collects_sources_once(self):
        text = workflow("test-deals.yml")
        self.assertNotIn("deals.run_steam", text)
        self.assertNotIn("deals.run_cheapshark", text)
        self.assertNotIn("deals.run_epic", text)
        self.assertNotIn("deals.run_all", text)
        self.assertEqual(text.count("python -m deals.build_feed"), 1)
        self.assertEqual(text.count("python -m deals.publish_wordpress"), 1)

    def test_social_is_consolidated(self):
        self.assertFalse((WORKFLOWS / "social-sunday.yml").exists())
        self.assertFalse((WORKFLOWS / "social-publish-now-once.yml").exists())
        social = workflow("social-test.yml")
        recovery = workflow("social-publish-recovery.yml")
        self.assertIn('timezone: "Europe/Paris"', social)
        self.assertIn('timezone: "Europe/Paris"', recovery)

    def test_duplicate_ci_is_consolidated(self):
        self.assertFalse((WORKFLOWS / "test-trending-seo.yml").exists())
        self.assertFalse((WORKFLOWS / "social-image-selection-ci.yml").exists())
        for name in (
            "news-quality-ci.yml",
            "seo-quality-ci.yml",
            "deals-quality-ci.yml",
            "reviews-quality-ci.yml",
            "social-quality-ci.yml",
            "acquisition-quality-ci.yml",
        ):
            with self.subTest(workflow=name):
                self.assertTrue((WORKFLOWS / name).exists(), name)

    def test_health_thresholds_match_content_cadence(self):
        text = workflow("content-health.yml")
        self.assertRegex(text, r'latest_post\(2,\s*"Actualités",\s*8\)')
        self.assertRegex(text, r'latest_post\(5,\s*"Tests & Avis",\s*30\)')
        self.assertIn("max_age_hours", text)

    def test_production_workflows_skip_pip_self_upgrade(self):
        for name in (
            "gamerquest.yml",
            "run-trending-seo-pipeline.yml",
            "test-deals.yml",
            "reviews.yml",
            "acquisition-shadow.yml",
            "social-test.yml",
        ):
            with self.subTest(workflow=name):
                self.assertNotIn("pip install --upgrade pip", workflow(name))


if __name__ == "__main__":
    unittest.main()
