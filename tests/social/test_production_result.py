import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class ProductionResultTests(unittest.TestCase):
    def report(self, requested, ready, allowed, publish='skipped', pending=''):
        text = (ROOT / '.github/workflows/social-test.yml').read_text()
        section = text.split('      - name: P0 social final status\n', 1)[1]
        script = section.split('        run: |\n', 1)[1].split('\n      - name:', 1)[0]
        script = '\n'.join(line[10:] for line in script.splitlines())
        values = {'github.event_name': 'schedule' if requested else 'workflow_dispatch',
            'inputs.publish_to_meta': 'false', 'steps.meta_preflight.outcome': 'success',
            'steps.wordpress_stage.outcome': 'success' if ready else 'skipped',
            'steps.groq_budget.outputs.allowed': 'true' if allowed else 'false',
            'steps.groq_budget.outputs.reason': 'reserved' if allowed else 'daily limit',
            'steps.social_generate.outcome': 'success',
            'steps.social_status.outputs.ready': 'true' if ready else 'false',
            'steps.social_status.outputs.status': 'ready' if ready else 'skipped',
            'steps.social_status.outputs.reason': 'social_budget_exhausted',
            'steps.meta_publish.outcome': publish,
            'steps.meta_pending.outputs.pending_count': pending,
            'steps.meta_pending.outputs.pending_platforms': 'instagram,facebook'}
        script = re.sub(r'\$\{\{\s*(.*?)\s*\}\}', lambda m: values.get(m[1], ''), script)
        with tempfile.TemporaryDirectory() as tmp:
            return subprocess.run(['bash', '-c', script], env={
                'GITHUB_STEP_SUMMARY': str(Path(tmp) / 'summary')},
                capture_output=True, text=True)

    def test_requested_generation_skip_is_not_success(self):
        for allowed in (True, False):
            result = self.report(True, False, allowed)
            self.assertEqual(result.returncode, 1, result.stdout)

    def test_generation_only_can_skip_without_reporting_publication(self):
        result = self.report(False, False, True)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('SOCIAL RESULT: SKIPPED', result.stdout)

    def test_completed_publish_is_success(self):
        result = self.report(True, True, True, 'success', '2')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn('SOCIAL RESULT: PUBLISHED', result.stdout)


if __name__ == '__main__':
    unittest.main()
