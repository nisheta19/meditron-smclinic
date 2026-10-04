import unittest
from unittest.mock import patch
import os
from pathlib import Path
import subprocess
import sys
from app.contracts import ContractError
from app.demo import run_demo


class DemoTests(unittest.TestCase):
    def test_missing_dependency_fails_before_http_start(self):
        with patch('app.demo.load_dictionary', side_effect=ContractError('PyYAML missing')), patch('app.demo.ThreadingHTTPServer') as server:
            with self.assertRaisesRegex(ContractError, 'PyYAML'):
                run_demo()
            server.assert_not_called()

    def test_cli_missing_yaml_has_actionable_error_without_traceback(self):
        env = dict(os.environ)
        env.pop('PYTHONPATH', None)
        env['PYTHONIOENCODING'] = 'utf-8'
        result = subprocess.run([sys.executable, '-S', '-m', 'app.demo'],
                                cwd=Path(__file__).resolve().parent.parent,
                                env=env, capture_output=True, encoding='utf-8')
        self.assertEqual(result.returncode, 2)
        self.assertIn('PyYAML', result.stderr)
        self.assertIn('.venv/Scripts/python.exe', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_real_http_complete_lifecycle(self):
        result = run_demo()
        self.assertTrue(result["passed"])
        self.assertEqual(result["uniqueResults"], 3)
        self.assertEqual([e["result"]["status"] for e in result["events"]], ["DONE", "DONE", "ANNULLED"])
        self.assertEqual(result["events"][0]["result"]["findings"][0]["attributes"]["sizeMm"], 8)
