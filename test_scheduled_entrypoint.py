"""Prevent the legacy auto-draft job from being re-enabled accidentally."""
from pathlib import Path
import unittest

class ScheduledEntrypointTests(unittest.TestCase):
    def test_scheduled_job_uses_candidate_selection(self):
        workflow = Path(".github/workflows/free-bot.yml").read_text()
        scheduled = workflow.split("- name: Scheduled command", 1)[1].split("\n      - name:", 1)[0]
        self.assertIn("run: python candidate_bot.py daily", scheduled)
        self.assertNotIn("free_bot.py", scheduled)

if __name__ == "__main__":
    unittest.main()
