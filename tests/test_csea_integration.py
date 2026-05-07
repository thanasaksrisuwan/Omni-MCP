import unittest
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts import mcp_server

class TestCSEAIntegration(unittest.TestCase):
    def test_csea_execute_command_allowed(self):
        # git status is allowlisted
        result = mcp_server.csea_execute_command("git status")
        self.assertEqual(result.get("status"), "ok")
        self.assertEqual(result.get("allowed"), True)
        self.assertIn("On branch", result.get("stdout", ""))

    def test_csea_execute_command_blocked(self):
        # rm -rf is blacklisted
        result = mcp_server.csea_execute_command("rm -rf .")
        self.assertEqual(result.get("status"), "blocked")
        self.assertEqual(result.get("allowed"), False)
        self.assertIn("blacklisted", result.get("reason", "").lower())

    def test_csea_execute_command_not_allowlisted(self):
        # unknown command
        result = mcp_server.csea_execute_command("unknown_command_xyz")
        self.assertEqual(result.get("status"), "blocked")
        self.assertEqual(result.get("allowed"), False)
        self.assertIn("not allowlisted", result.get("reason", "").lower())

if __name__ == '__main__':
    unittest.main()
