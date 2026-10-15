"""Offline external-write journeys with real Git ancestry and a GitHub double."""

import contextlib
import copy
import hashlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import finish_delivery
from review_gate import IDENTITY, digest, spec_digest


class FakeMutationProcess:
    def __init__(self, action, drain_failure=False):
        self.action = action
        self.returncode = None
        self.drain_failure = drain_failure

    def communicate(self, timeout=None):
        if self.returncode is not None:
            if self.drain_failure:
                raise subprocess.TimeoutExpired("fake gh drain", timeout)
            return "", ""
        try:
            self.returncode, stdout, stderr = self.action()
            return stdout, stderr
        except subprocess.CalledProcessError as error:
            self.returncode = error.returncode
            return error.output or "", error.stderr or ""

    def kill(self):
        self.returncode = -9


class FinishDeliveryTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[3] / ".career-ops-delivery-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.checkout = self.root / "checkout"
        self.checkout.mkdir()
        self.real_output = subprocess.check_output
        self.real_popen = subprocess.Popen
        self.git("init", "-q")
        self.git("-c", "user.name=Delivery Test", "-c", "user.email=test@example.invalid",
                 "commit", "--allow-empty", "-qm", "base")
        self.base = self.git("rev-parse", "HEAD")
        (self.checkout / "feature.txt").write_text("reviewed feature\n", encoding="utf-8")
        self.git("add", "feature.txt")
        self.git("-c", "user.name=Delivery Test", "-c", "user.email=test@example.invalid",
                 "commit", "-qm", "candidate")
        self.head = self.git("rev-parse", "HEAD")
        self.tree = self.git("rev-parse", "HEAD^{tree}")
        self.config = dict(repo="example/another-project", merge_method="squash",
                           review_skill="matt-code-review",
                           actual_models={"opus": "claude-opus-5-5"})
        self.request = dict(repo=self.config["repo"], issue=51, parent_issue=40, pr=100, round=1,
                            base_sha=self.base, target_base_sha=self.base, head_sha=self.head,
                            target_branch="release/web", review_model="opus",
                            expected_model="claude-opus-5-5", review_skill="matt-code-review",
                            criteria=["A complete requirement"],
                            checks=[dict(name="check", host="linux", argv=["check"], timeout=10)])
        self.report = {key: self.request[key] for key in IDENTITY}
        self.report.update(verdict="PASS", findings=[], limitations=["Offline fixtures only"],
                           standards=dict(status="PASS", summary="Standards reviewed"),
                           spec=dict(status="PASS", summary="Specification reviewed"),
                           acceptance=[dict(index=1, status="PASS", evidence="linux-check.log")])
        self.codex = {**copy.deepcopy(self.report), "request_digest": digest(self.request)}
        self.spec = dict(title="A bounded ticket", body="A complete requirement", comments=[])
        self.evidence = dict(request_digest=digest(self.request), head_before=self.head,
                             head_after=self.head, dirty_before="", dirty_after="",
                             process_exit=0, model_error=False, session_id="session",
                             init_session_id="session", skill=dict(name="matt-code-review", loaded=True),
                             parent_models=["claude-opus-5-5"],
                             agents_invoked=["standards-reviewer", "spec-reviewer"],
                             subagent_models={"a": ["claude-opus-5-5"], "b": ["claude-opus-5-5"]},
                             issue_digest=spec_digest(self.spec), parent_digest=spec_digest(self.spec),
                             checks={"check": dict(exit_code=0, host="linux", argv=["check"],
                                                   head_sha=self.head, log="linux-check.log")}, axes={})
        self.folder = self.root / "review-round"
        self.folder.mkdir()
        (self.folder / "linux-check.log").write_text("Independent check passed\n", encoding="utf-8")
        for axis in ("standards", "spec"):
            self.evidence["axes"][axis] = dict(tool_use_id=axis, agent_id=axis, completed=True,
                models=["claude-opus-5-5"], status="PASS", summary="Independent report", findings=[],
                report=f"{axis}-child.json", raw_report=f"{axis}-child.txt",
                transcript=f"{axis}-transcript.jsonl")
            for suffix in ("json", "txt"):
                (self.folder / f"{axis}-child.{suffix}").write_text("{}", encoding="utf-8")
            (self.folder / f"{axis}-transcript.jsonl").write_text("{}\n", encoding="utf-8")
        self.save_receipt()
        self.pr_state = "OPEN"
        self.issue_state = "OPEN"
        self.pr_head = self.head
        self.pr_base = self.base
        self.live_base = self.base
        self.target_branch = "release/web"
        self.merge_sha = "e" * 40
        self.merge_tree = self.tree
        self.merge_parents = [self.base]
        self.comments = []
        self.hide_comments = False
        self.omit_comment_in_issue_view = False
        self.mutations = []
        self.ack_loss = None
        self.before_send_failure = None
        self.api_failure = None
        self.communication_timeout = None
        self.cleanup_failure = False
        self.drain_failure = False
        self.rest_requests = []
        self.ignore_close = False
        self.draft = False
        self.mergeable = "MERGEABLE"
        self.checks = []

    def git(self, *args):
        return self.real_output(["git", "-c", "commit.gpgsign=false", *args], cwd=self.checkout, text=True, encoding="utf-8").strip()

    def save_receipt(self):
        for name, value in (("request", self.request), ("report", self.report),
                            ("status", dict(verdict="PASS")), ("codex-acceptance", self.codex)):
            (self.folder / f"{name}.json").write_text(json.dumps(value), encoding="utf-8")
        self.evidence["files"] = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.folder.iterdir()
            if path.name not in ("evidence.json", "status.json", "codex-acceptance.json")
        }
        (self.folder / "evidence.json").write_text(json.dumps(self.evidence), encoding="utf-8")

    def external_output(self, command, **kwargs):
        if command[0] != "gh":
            return self.real_output(command, **kwargs)
        args = command[1:]
        if args[:2] == ["issue", "view"]:
            value = {**copy.deepcopy(self.spec), "state": self.issue_state}
            if int(args[2]) == self.request["issue"]:
                value["comments"] = [] if self.hide_comments or self.omit_comment_in_issue_view else copy.deepcopy(self.comments)
            return json.dumps(value)
        if args[:2] == ["pr", "view"]:
            return json.dumps(dict(headRefOid=self.pr_head, baseRefName=self.target_branch,
                state=self.pr_state, mergeCommit={"oid": self.merge_sha} if self.pr_state == "MERGED" else None,
                isDraft=self.draft, mergeable=self.mergeable, statusCheckRollup=self.checks))
        if args[0] == "api":
            route = args[1]
            prefix = f"repos/{self.config['repo']}"
            if route == prefix:
                return json.dumps(dict(allow_squash_merge=True))
            if route == f"{prefix}/pulls/{self.request['pr']}":
                return json.dumps(dict(head=dict(sha=self.pr_head), base=dict(sha=self.pr_base, ref=self.target_branch)))
            if route == f"{prefix}/git/ref/heads/{self.target_branch}":
                return json.dumps(dict(object=dict(sha=self.live_base)))
            if route == f"{prefix}/commits/{self.head}":
                return json.dumps(dict(commit=dict(tree=dict(sha=self.tree))))
            if route == f"{prefix}/commits/{self.merge_sha}":
                return json.dumps(dict(commit=dict(tree=dict(sha=self.merge_tree)),
                    parents=[dict(sha=sha) for sha in self.merge_parents]))
            if route == f"{prefix}/issues/{self.request['issue']}/comments?per_page=100":
                self.assertIn("--paginate", args)
                self.assertNotIn("--slurp", args)
                self.assertEqual(args[args.index("--jq") + 1], ".[]")
                return "\n".join(json.dumps(comment) for comment in ([] if self.hide_comments else self.comments))
            raise AssertionError(f"Unexpected read: {args}")
        raise AssertionError(f"Unexpected legacy mutation: {args}")

    def external_popen(self, command, **kwargs):
        if command[0] != "gh":
            return self.real_popen(command, **kwargs)
        self.assertEqual(command[1], "api")
        method, endpoint = command[command.index("--method") + 1], command[2]
        payload = json.loads(Path(command[command.index("--input") + 1]).read_text(encoding="utf-8"))
        operations = {"PUT": "pr merge", "POST": "issue comment", "PATCH": "issue close"}
        operation = operations[method]
        prefix = f"repos/{self.config['repo']}"
        self.assertEqual(endpoint, {"PUT": f"{prefix}/pulls/{self.request['pr']}/merge",
                                   "POST": f"{prefix}/issues/{self.request['issue']}/comments",
                                   "PATCH": f"{prefix}/issues/{self.request['issue']}"}[method])
        self.assertIn("--include", command)
        self.assertEqual(command[command.index("--hostname") + 1], "github.com")
        self.assertEqual(kwargs["env"]["GH_DEBUG"], "")
        self.rest_requests.append(dict(command=command, method=method, endpoint=endpoint, payload=payload))
        if self.before_send_failure == operation:
            self.before_send_failure = None
            raise FileNotFoundError("The GitHub command could not start")

        def response():
            if self.communication_timeout == operation:
                self.communication_timeout = None
                raise subprocess.TimeoutExpired(command, 60)
            if self.api_failure and self.api_failure[0] == operation:
                _, stdout, stderr = self.api_failure
                self.api_failure = None
                return 1, stdout, stderr
            self.mutations.append(operation.split())
            if operation == "pr merge":
                self.assertEqual(payload, dict(sha=self.head, merge_method="squash"))
                self.pr_state = "MERGED"
                self.live_base = self.merge_sha
            elif operation == "issue comment":
                self.comments.append(dict(id="comment-1", body=payload["body"]))
            elif operation == "issue close" and not self.ignore_close:
                self.assertEqual(payload, dict(state="closed", state_reason="completed"))
                self.issue_state = "CLOSED"
            if self.ack_loss == operation:
                self.ack_loss = None
                return 1, "", "Connection lost after effect"
            return 0, 'HTTP/2.0 200 OK\n\n{"acknowledged":true}', ""

        return FakeMutationProcess(response, self.drain_failure)

    def finish(self, reconcile_operation=None):
        def cleanup(process):
            if self.cleanup_failure:
                raise RuntimeError("Injected process cleanup failure")
            process.kill()

        with patch("subprocess.check_output", side_effect=self.external_output), \
                patch("subprocess.Popen", side_effect=self.external_popen), \
                patch("finish_delivery.terminate_tree", side_effect=cleanup, create=True), \
                contextlib.redirect_stdout(io.StringIO()):
            return finish_delivery.finish(self.config, self.folder, self.checkout,
                                           reconcile_operation=reconcile_operation)

    def test_accepted_candidate_merges_and_closes_once_across_restarts(self):
        before = {path.name: path.read_bytes() for path in self.folder.iterdir()}
        result = self.finish()
        first_writes = copy.deepcopy(self.mutations)
        self.assertTrue(result["closed"])
        self.assertEqual(result["merge_sha"], self.merge_sha)
        self.assertEqual(result["tree"], self.tree)
        self.assertEqual(result["parent"], self.base)
        self.assertEqual(self.finish(), result)
        self.assertEqual(self.mutations, first_writes)
        self.assertEqual(len(self.comments), 1)
        self.assertEqual(self.issue_state, "CLOSED")
        self.assertEqual({path.name: path.read_bytes() for path in self.folder.iterdir()}, before)
        self.assertEqual(self.rest_requests[0]["method"], "PUT")
        self.assertEqual(self.rest_requests[0]["payload"], dict(sha=self.head, merge_method="squash"))
        self.assertNotIn("--admin", self.rest_requests[0]["command"])

    def test_unstarted_github_command_can_retry_without_sticking_pending(self):
        self.before_send_failure = "pr merge"
        with self.assertRaises(OSError):
            self.finish()
        self.assertEqual(self.mutations, [])
        self.assertTrue(self.finish()["closed"])

    def finish_state(self):
        return json.loads((self.root / "review-round.finish/state.json").read_text(encoding="utf-8"))

    def test_unstarted_comment_and_close_commands_can_retry_without_duplicates(self):
        for operation in ("issue comment", "issue close"):
            self.before_send_failure = operation
            with self.assertRaises(OSError):
                self.finish()
            state = self.finish_state()
            self.assertIsNone(state["pending"])
            self.assertEqual(state["attempts"][-1]["outcome"], "not_sent")
            self.assertEqual(state["attempts"][-1]["reason"], "process_not_started")
        self.assertTrue(self.finish()["closed"])
        self.assertEqual(len(self.comments), 1)
        self.assertEqual(sum(args == ["issue", "close"] for args in self.mutations), 1)

    def test_single_request_dns_and_explicit_rejections_allow_safe_comment_retry(self):
        endpoint = f"repos/{self.config['repo']}/issues/{self.request['issue']}/comments"
        scenarios = [("", f'Post "https://api.github.com/{endpoint}": dial tcp: lookup api.github.com: no such host\n', "not_sent")]
        scenarios.extend((f"HTTP/2.0 {status} Rejected\n\n{{}}", "Server rejected this request", "rejected")
                         for status in (401, 403, 409, 422, 429))
        for stdout, stderr, expected in scenarios:
            with self.subTest(expected=expected, stdout=stdout):
                self.api_failure = ("issue comment", stdout, stderr)
                with self.assertRaises(subprocess.CalledProcessError):
                    self.finish()
                state = self.finish_state()
                self.assertIsNone(state["pending"])
                self.assertEqual(state["attempts"][-1]["outcome"], expected)
                self.assertEqual(self.comments, [])
        self.assertTrue(self.finish()["closed"])
        self.assertEqual(len(self.comments), 1)

    def test_ambiguous_comment_failure_stays_pending_and_has_no_retry_override(self):
        self.api_failure = ("issue comment", "HTTP/2.0 503 Unavailable\n\n{}", "response lost")
        with self.assertRaises(subprocess.CalledProcessError):
            self.finish()
        self.assertEqual(self.finish_state()["pending"], "comment")
        self.assertEqual(self.finish_state()["attempts"][-1]["outcome"], "unknown")
        calls = len(self.rest_requests)
        for operation in (None, "merge", "close"):
            with self.assertRaisesRegex(RuntimeError, "comment outcome"):
                self.finish(operation)
        with self.assertRaisesRegex(ValueError, "Only exact-identity"):
            self.finish("comment")
        self.assertEqual(len(self.rest_requests), calls)
        self.assertEqual(self.issue_state, "OPEN")

    def test_comment_timeout_preserves_unknown_attempt(self):
        self.communication_timeout = "issue comment"
        with self.assertRaises(subprocess.TimeoutExpired):
            self.finish()
        state = self.finish_state()
        self.assertEqual(state["pending"], "comment")
        self.assertEqual(state["attempts"][-1]["reason"], "process_interrupted")
        with self.assertRaisesRegex(RuntimeError, "comment outcome"):
            self.finish()
        self.assertEqual(len(self.rest_requests), 2)

    def test_reconcile_merge_rechecks_current_gates_then_retries_exact_identity(self):
        self.api_failure = ("pr merge", "", "Connection closed without response")
        with self.assertRaises(subprocess.CalledProcessError):
            self.finish()
        for field, changed in (("pr_head", "f" * 40), ("live_base", "f" * 40),
                               ("checks", [dict(__typename="CheckRun", status="IN_PROGRESS")])):
            original = getattr(self, field)
            setattr(self, field, changed)
            with self.assertRaises(RuntimeError):
                self.finish("merge")
            self.assertEqual(len(self.rest_requests), 1)
            setattr(self, field, original)
        original_body = self.spec["body"]
        self.spec["body"] = "Requirement changed"
        with self.assertRaisesRegex(RuntimeError, "specification changed"):
            self.finish("merge")
        self.spec["body"] = original_body
        self.assertTrue(self.finish("merge")["closed"])
        self.assertEqual(self.rest_requests[0]["payload"], self.rest_requests[1]["payload"])
        self.assertEqual(len(self.finish_state()["reconciliations"]), 1)

    def test_reconcile_close_requires_verified_merge_and_existing_comment(self):
        self.api_failure = ("issue close", "", "Connection closed without response")
        with self.assertRaises(subprocess.CalledProcessError):
            self.finish()
        self.merge_tree = "f" * 40
        with self.assertRaisesRegex(RuntimeError, "do not close"):
            self.finish("close")
        self.assertEqual(len(self.rest_requests), 3)
        self.merge_tree = self.tree
        self.assertTrue(self.finish("close")["closed"])
        self.assertEqual(len(self.comments), 1)
        self.assertEqual(self.finish_state()["reconciliations"][-1]["operation"], "close")

    def test_comment_pagination_recovers_lost_ack_even_if_issue_view_omits_it(self):
        self.ack_loss = "issue comment"
        with self.assertRaises(subprocess.CalledProcessError):
            self.finish()
        self.omit_comment_in_issue_view = True
        self.assertTrue(self.finish()["closed"])
        self.assertEqual(len(self.comments), 1)

    def test_attempt_logs_are_redacted_and_bound_to_persisted_hashes(self):
        secret = "ghp_testsecret1234567890"
        self.api_failure = ("pr merge", "HTTP/2.0 401 Unauthorized\nSet-Cookie: session=private\n\n{}",
                            f"Authorization: Bearer private\n{secret}\n")
        with self.assertRaises(subprocess.CalledProcessError) as failure:
            self.finish()
        self.assertNotIn(secret, failure.exception.stderr)
        attempt = self.finish_state()["attempts"][-1]
        folder = self.root / "review-round.finish/attempts" / attempt["id"]
        for name in ("stdout", "stderr"):
            data = (folder / f"{name}.log").read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), attempt[f"{name}_sha256"])
            self.assertNotIn(b"private", data)
            self.assertNotIn(secret.encode(), data)

    def test_http_status_text_in_nonresponse_output_cannot_authorize_comment_retry(self):
        self.api_failure = ("issue comment", "Unexpected output\nHTTP/2.0 403 Rejected\n\n{}", "response unknown")
        with self.assertRaises(subprocess.CalledProcessError):
            self.finish()
        self.assertEqual(self.finish_state()["attempts"][-1]["outcome"], "unknown")
        with self.assertRaisesRegex(RuntimeError, "comment outcome"):
            self.finish()

    def test_later_unknown_comment_intent_cannot_be_replaced_by_stale_open_pr(self):
        self.ack_loss = "issue comment"
        with self.assertRaises(subprocess.CalledProcessError):
            self.finish()
        self.hide_comments = True
        self.pr_state, self.live_base = "OPEN", self.base
        writes = len(self.rest_requests)
        for operation in (None, "merge", "close"):
            with self.assertRaisesRegex(RuntimeError, "earlier merge phase"):
                self.finish(operation)
            self.assertEqual(self.finish_state()["pending"], "comment")
            self.assertEqual(len(self.rest_requests), writes)
        self.pr_state = "MERGED"
        self.hide_comments = False
        self.assertTrue(self.finish()["closed"])
        self.assertEqual(len(self.comments), 1)

    def test_persisted_not_sent_result_recovers_after_state_update_crash(self):
        original_write = finish_delivery.write
        crashed = False

        def crash_between_records(path, value):
            nonlocal crashed
            attempts = value.get("attempts", [])
            if Path(path).name == "state.json" and attempts and attempts[-1].get("outcome") == "not_sent" and not crashed:
                crashed = True
                raise OSError("Injected interruption after result persisted")
            return original_write(path, value)

        self.before_send_failure = "issue comment"
        with patch("finish_delivery.write", side_effect=crash_between_records):
            with self.assertRaises(OSError):
                self.finish()
        self.assertTrue(crashed)
        self.assertEqual(self.finish_state()["pending"], "comment")
        self.assertTrue(self.finish()["closed"])
        self.assertEqual(len(self.comments), 1)

    def test_failed_process_cleanup_blocks_even_explicit_reconciliation(self):
        self.communication_timeout, self.cleanup_failure = "pr merge", True
        with self.assertRaisesRegex(RuntimeError, "cleanup"):
            self.finish()
        blocked = self.root / "review-round.finish/cleanup-blocked.json"
        self.assertTrue(blocked.exists())
        writes = len(self.rest_requests)
        self.cleanup_failure = False
        with self.assertRaisesRegex(RuntimeError, "cleanup unresolved"):
            self.finish("merge")
        self.assertEqual(len(self.rest_requests), writes)

    def test_failed_drain_after_termination_also_blocks_reconciliation(self):
        self.communication_timeout, self.drain_failure = "pr merge", True
        with self.assertRaisesRegex(RuntimeError, "cleanup unresolved"):
            self.finish()
        self.assertTrue((self.root / "review-round.finish/cleanup-blocked.json").exists())
        self.assertEqual(self.finish_state()["attempts"][-1]["reason"], "cleanup_failed")
        with self.assertRaisesRegex(RuntimeError, "cleanup unresolved"):
            self.finish("merge")
        self.assertEqual(len(self.rest_requests), 1)

    def test_lost_comment_ack_waits_for_receipt_without_reposting(self):
        self.ack_loss = "issue comment"
        with self.assertRaises(subprocess.CalledProcessError):
            self.finish()
        self.hide_comments = True
        with self.assertRaisesRegex(RuntimeError, "comment"):
            self.finish()
        self.assertEqual(sum(args[:2] == ["issue", "comment"] for args in self.mutations), 1)
        self.assertEqual(self.issue_state, "OPEN")
        self.hide_comments = False
        self.assertTrue(self.finish()["closed"])

    def test_codex_empty_evidence_never_authorizes_merge(self):
        self.codex["acceptance"][0]["evidence"] = " \n "
        self.save_receipt()
        with self.assertRaisesRegex(RuntimeError, "Codex"):
            self.finish()
        self.assertEqual(self.mutations, [])

    def test_lost_merge_ack_resumes_after_automatic_issue_closure(self):
        self.ack_loss = "pr merge"
        with self.assertRaises(subprocess.CalledProcessError):
            self.finish()
        self.issue_state = "CLOSED"  # GitHub may apply a PR's Closes keyword.
        self.assertFalse((self.root / "review-round.finish/closure.json").exists())
        result = self.finish()
        self.assertTrue(result["closed"])
        self.assertEqual(sum(args[:2] == ["pr", "merge"] for args in self.mutations), 1)
        self.assertEqual(sum(args[:2] == ["issue", "close"] for args in self.mutations), 0)
        self.assertEqual(len(self.comments), 1)

    def test_lost_merge_ack_with_old_readback_never_repeats_merge(self):
        self.ack_loss = "pr merge"
        with self.assertRaises(subprocess.CalledProcessError):
            self.finish()
        self.pr_state = "OPEN"
        self.live_base = self.base
        with self.assertRaisesRegex(RuntimeError, "Merge outcome"):
            self.finish()
        self.assertEqual(sum(args[:2] == ["pr", "merge"] for args in self.mutations), 1)
        self.pr_state = "MERGED"
        self.assertTrue(self.finish()["closed"])

    def test_lost_close_ack_is_reconciled_without_repeating_close(self):
        self.ack_loss = "issue close"
        with self.assertRaises(subprocess.CalledProcessError):
            self.finish()
        self.assertTrue(self.finish()["closed"])
        self.assertEqual(sum(args[:2] == ["issue", "close"] for args in self.mutations), 1)

    def test_lost_close_ack_with_old_readback_never_repeats_close(self):
        self.ack_loss = "issue close"
        with self.assertRaises(subprocess.CalledProcessError):
            self.finish()
        self.issue_state = "OPEN"
        with self.assertRaisesRegex(RuntimeError, "closure outcome"):
            self.finish()
        self.assertEqual(sum(args[:2] == ["issue", "close"] for args in self.mutations), 1)
        self.issue_state = "CLOSED"
        self.assertTrue(self.finish()["closed"])

    def test_confirmed_comment_temporarily_absent_is_not_reposted(self):
        self.ack_loss = "issue close"
        with self.assertRaises(subprocess.CalledProcessError):
            self.finish()
        self.hide_comments = True
        with self.assertRaisesRegex(RuntimeError, "comment"):
            self.finish()
        self.assertEqual(sum(args[:2] == ["issue", "comment"] for args in self.mutations), 1)
        self.hide_comments = False
        self.assertTrue(self.finish()["closed"])

    def test_unconfirmed_close_has_no_closure_receipt_and_can_resume(self):
        self.ignore_close = True
        with self.assertRaisesRegex(RuntimeError, "closure not confirmed"):
            self.finish()
        self.assertFalse((self.root / "review-round.finish/closure.json").exists())
        self.ignore_close = False
        self.issue_state = "CLOSED"
        self.assertTrue(self.finish()["closed"])
        self.assertEqual(len(self.comments), 1)
        self.assertEqual(sum(args[:2] == ["pr", "merge"] for args in self.mutations), 1)

    def test_live_candidate_and_ci_drift_never_merge(self):
        for field, changed in (("pr_head", "f" * 40), ("pr_base", "f" * 40),
                               ("live_base", "f" * 40), ("target_branch", "another"),
                               ("draft", True), ("mergeable", "UNKNOWN"),
                               ("checks", [dict(__typename="CheckRun", status="IN_PROGRESS")])):
            with self.subTest(field=field):
                original = getattr(self, field)
                setattr(self, field, changed)
                with self.assertRaises(RuntimeError):
                    self.finish()
                self.assertEqual(self.mutations, [])
                setattr(self, field, original)

    def test_changed_specification_never_merges(self):
        self.spec["body"] = "A newly added requirement"
        with self.assertRaisesRegex(RuntimeError, "specification changed"):
            self.finish()
        self.assertEqual(self.mutations, [])

    def test_failed_review_and_changed_evidence_never_merge(self):
        self.report["verdict"] = "CHANGES_REQUIRED"
        self.save_receipt()
        with self.assertRaisesRegex(RuntimeError, "gate"):
            self.finish()
        self.report["verdict"] = "PASS"
        self.save_receipt()
        (self.folder / "linux-check.log").write_text("Tampered", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "Changed evidence"):
            self.finish()
        self.assertEqual(self.mutations, [])

    def test_missing_stale_or_blocking_codex_agreement_never_merges(self):
        original = copy.deepcopy(self.codex)
        for change in (dict(head_sha="f" * 40), dict(request_digest="stale"),
                       dict(verdict="FAIL"), dict(findings=[dict(blocking=True)]),
                       dict(acceptance=[])):
            with self.subTest(change=change):
                self.codex = {**original, **change}
                self.save_receipt()
                with self.assertRaisesRegex(RuntimeError, "Codex"):
                    self.finish()
                self.assertEqual(self.mutations, [])
        (self.folder / "codex-acceptance.json").unlink()
        with self.assertRaises(FileNotFoundError):
            self.finish()
        self.assertEqual(self.mutations, [])

    def test_fable_cannot_substitute_for_opus_acceptance(self):
        self.config["actual_models"]["claude-fable-5-1"] = "claude-fable-5-1"
        self.request.update(review_model="claude-fable-5-1", expected_model="claude-fable-5-1")
        self.save_receipt()
        with self.assertRaisesRegex(RuntimeError, "Fable"):
            self.finish()
        self.assertEqual(self.mutations, [])

    def test_target_base_not_in_reviewed_candidate_never_merges(self):
        self.git("-c", "user.name=Delivery Test", "-c", "user.email=test@example.invalid",
                 "commit", "--allow-empty", "-qm", "later target")
        later = self.git("rev-parse", "HEAD")
        self.request["target_base_sha"] = later
        self.report["target_base_sha"] = later
        self.codex.update(target_base_sha=later, request_digest=digest(self.request))
        self.evidence["request_digest"] = digest(self.request)
        self.pr_base = self.live_base = later
        self.save_receipt()
        with self.assertRaises(subprocess.CalledProcessError):
            self.finish()
        self.assertEqual(self.mutations, [])

    def test_wrong_squash_parent_or_tree_never_publishes_or_closes(self):
        for field, changed in (("merge_tree", "f" * 40), ("merge_parents", [self.head]),
                               ("merge_parents", [self.base, self.head])):
            with self.subTest(field=field, changed=changed):
                original = getattr(self, field)
                setattr(self, field, changed)
                with self.assertRaisesRegex(RuntimeError, "do not close"):
                    self.finish()
                self.assertEqual(self.comments, [])
                self.assertEqual(self.issue_state, "OPEN")
                self.assertFalse((self.root / "review-round.finish/closure.json").exists())
                setattr(self, field, original)
        self.assertEqual(sum(args[:2] == ["pr", "merge"] for args in self.mutations), 1)

    def test_modified_published_receipt_is_never_ignored_as_our_comment(self):
        self.finish()
        writes = copy.deepcopy(self.mutations)
        self.comments[0]["body"] += "Changed acceptance claim\n"
        with self.assertRaisesRegex(RuntimeError, "comment changed"):
            self.finish()
        self.assertEqual(self.mutations, writes)

    def test_acceptance_comment_hash_is_durable_and_line_endings_are_normalized(self):
        result = self.finish()
        state = json.loads((self.root / "review-round.finish/state.json").read_text(encoding="utf-8"))
        body = self.comments[0]["body"]
        self.assertEqual(result["comment_sha256"], hashlib.sha256(body.encode("utf-8")).hexdigest())
        self.assertEqual(state["comment"]["body_sha256"], result["comment_sha256"])
        self.comments[0]["body"] = body.replace("\n", "\r\n")
        self.assertEqual(self.finish(), result)


if __name__ == "__main__":
    unittest.main()
