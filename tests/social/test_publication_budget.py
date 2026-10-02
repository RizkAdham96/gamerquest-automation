import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import groq_budget
from social.ai_client import call_grok


class Response:
    def __init__(self, usage):
        self.usage = usage

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        payload = {'choices': [{'message': {'content': '{"valid":true}'}, 'finish_reason': 'stop'}]}
        if self.usage is not None:
            payload['usage'] = self.usage
        return json.dumps(payload).encode()


class PublicationBudgetTests(unittest.TestCase):
    def setUp(self):
        groq_budget.reset_local_counters()

    def tearDown(self):
        groq_budget.reset_local_counters()

    def test_completed_calls_release_unused_allowance_for_factual_repair(self):
        # Three calls reserve 2,000 each, but each actually uses 1,100.
        # A 4,200 run allowance must admit all three (3,300 actual tokens).
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            'GROQ_API_KEY': 'test-key', 'GROQ_RUN_TOKEN_BUDGET': '4200',
            'GROQ_TPM_CEILING': '6000', 'GROQ_USAGE_FILE': str(Path(tmp) / 'usage.json'),
        }), patch('social.ai_client.urllib.request.urlopen', side_effect=lambda *a, **k: Response({
            'prompt_tokens': 1000, 'completion_tokens': 100, 'total_tokens': 1100,
        })):
            for _ in range(3):
                self.assertEqual(call_grok('x' * 3000, max_tokens=1000), '{"valid":true}')
            usage = json.loads((Path(tmp) / 'usage.json').read_text())
            self.assertEqual(usage['estimated_tokens'], 3300)
            self.assertEqual(usage['calls'], 3)

    def test_missing_or_invalid_usage_keeps_conservative_allowance(self):
        for usage in (None, {}, {'total_tokens': 0}, {'total_tokens': True},
                      {'total_tokens': -100}, {'total_tokens': '10'},
                      {'prompt_tokens': 1000, 'completion_tokens': 100, 'total_tokens': 10}):
            with self.subTest(usage=usage):
                groq_budget.reset_local_counters()
                with patch.dict(os.environ, {'GROQ_API_KEY': 'test-key',
                    'GROQ_RUN_TOKEN_BUDGET': '2000', 'GROQ_TPM_CEILING': '6000',
                    'GROQ_USAGE_FILE': ''}), patch('social.ai_client.urllib.request.urlopen',
                    side_effect=lambda *a, **k: Response(usage)):
                    call_grok('x' * 3000, max_tokens=1000)
                    with self.assertRaises(RuntimeError):
                        call_grok('x' * 3000, max_tokens=1000)


if __name__ == '__main__':
    unittest.main()
