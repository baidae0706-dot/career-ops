"""Live candidate checks retain gh 2.45 compatibility and enforce naming."""

import copy
import json
import unittest
from unittest.mock import patch

from delivery import live_candidate


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.config = {"repo": "test/project"}
        self.req = dict(issue=1, pr=147, head_sha="a" * 40,
                        target_base_sha="b" * 40, target_branch="main")
        self.issue = dict(number=1, title="chore(delivery): durable workflow")
        self.pr = dict(headRefOid="a" * 40, headRefName="chore/issue-1-delivery",
                       title=self.issue["title"], baseRefName="main", state="OPEN",
                       isDraft=False, mergeable="MERGEABLE",
                       statusCheckRollup=[{"status": "COMPLETED"}])
        self.api = dict(title=self.pr["title"], head=dict(sha="a" * 40, ref=self.pr["headRefName"]),
                        base=dict(sha="b" * 40, ref="main"))

    def call(self):
        def github(config, *args):
            return copy.deepcopy(self.pr if args[0] == "pr" else self.issue)
        with patch("delivery.gh", side_effect=github), \
                patch("delivery.output", return_value=json.dumps(self.api)):
            return live_candidate(self.config, self.req)

    def test_older_cli_preserves_identity_and_checks(self):
        result = self.call()
        self.assertEqual(result["baseRefOid"], "b" * 40)
        self.assertEqual(result["statusCheckRollup"], self.pr["statusCheckRollup"])

    def test_target_base_change_rejected(self):
        self.api["base"]["sha"] = "c" * 40
        with self.assertRaisesRegex(RuntimeError, "differs from pinned"):
            self.call()

    def test_head_read_race_rejected(self):
        self.api["head"]["sha"] = "c" * 40
        with self.assertRaisesRegex(RuntimeError, "between metadata reads"):
            self.call()

    def test_target_branch_read_race_rejected(self):
        self.api["base"]["ref"] = "other"
        with self.assertRaisesRegex(RuntimeError, "between metadata reads"):
            self.call()

    def test_missing_identity_is_not_accepted(self):
        del self.api["base"]["sha"]
        with self.assertRaises(KeyError):
            self.call()

    def test_live_issue_and_pr_titles_must_follow_convention_and_match(self):
        for title in ("Unnamed work", "chore(delivery): ", "chore(delivery): durable workflow\nextra"):
            with self.subTest(title=title):
                self.issue["title"] = self.pr["title"] = self.api["title"] = title
                with self.assertRaises(ValueError):
                    self.call()
        self.issue["title"] = "chore(delivery): original outcome"
        self.pr["title"] = self.api["title"] = "chore(delivery): different outcome"
        with self.assertRaisesRegex(ValueError, "match"):
            self.call()

    def test_live_branch_must_identify_the_same_issue(self):
        for name in ("main", "chore/issue-2-delivery", "chore/issue-1-", "chore/issue-1-Uppercase"):
            with self.subTest(branch=name):
                self.pr["headRefName"] = self.api["head"]["ref"] = name
                with self.assertRaises(ValueError):
                    self.call()

    def test_live_issue_response_must_identify_the_requested_issue(self):
        self.issue["number"] = 2
        with self.assertRaisesRegex(ValueError, "Issue"):
            self.call()


if __name__ == "__main__":
    unittest.main()
