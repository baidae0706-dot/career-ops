"""Delivery decisions are exercised through the durable command-line boundary."""
import json
import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from delivery import files_index, write, run_id
from review_gate import IDENTITY, digest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/delivery/coordinator.py"


class CoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root / "project.json"
        self.config.write_text(json.dumps({"repo": "test/project", "merge_method": "squash"}))
        self.state = self.root / "state.json"
        self.queue = self.root / "queue.json"
        self.queue.write_text(json.dumps({"authorization": "User authorized implement, review, repair, merge and close", "coordinator_thread": "owner", "issues": [
            {"issue": 1, "title": "chore(delivery): durable workflow", "dependencies": []},
            {"issue": 2, "title": "feat(web): confirm JD", "dependencies": [1]}]}))

    def candidate(self):
        checkout = self.root / "checkout"
        checkout.mkdir()
        def git(*args):
            return subprocess.check_output(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false", *args],
                                           cwd=checkout, text=True, stderr=subprocess.DEVNULL).strip()
        git("init", "-b", "chore/issue-1-delivery")
        (checkout / "source.txt").write_text("original")
        git("add", ".")
        git("commit", "-m", "base")
        base = git("rev-parse", "HEAD")
        (checkout / "source.txt").write_text("candidate")
        git("commit", "-am", "candidate")
        head = git("rev-parse", "HEAD")
        config = json.loads(self.config.read_text())
        config.update(review_skill="matt-code-review", actual_models={"opus": "claude-opus-5-5", "claude-fable-5-1":"claude-fable-5-1"})
        self.config.write_text(json.dumps(config))
        request = dict(repo="test/project", issue=1, pr=8, round=1, base_sha=base, head_sha=head,
                       target_base_sha=base, target_branch="main", criteria=["Durable single writer"],
                       review_model="opus", expected_model="claude-opus-5-5", review_skill="matt-code-review",
                       checks=[dict(name="checks", host="windows", argv=["check"], timeout=10)])
        path = self.root / "request.json"
        path.write_text(json.dumps(request))
        self.run_cli("init", self.queue)
        self.run_cli("claim", "--issue", 1, "--owner", "codex-thread", "--operation", "claim-1")
        return checkout, path, request

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *args, success=True):
        result = subprocess.run([sys.executable, str(SCRIPT), "--config", str(self.config),
                                 "--state", str(self.state), *map(str, args)], text=True, capture_output=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0)
        return result

    def test_restart_and_duplicate_claim_keep_one_writer_and_dependencies(self):
        self.run_cli("init", self.queue)
        self.assertEqual(self.run_cli("next")["issue"], 1)
        first = self.run_cli("claim", "--issue", 1, "--owner", "codex-thread", "--operation", "claim-1")
        repeated = self.run_cli("claim", "--issue", 1, "--owner", "codex-thread", "--operation", "claim-1")
        self.assertEqual(first, repeated)
        self.run_cli("claim", "--issue", 2, "--owner", "other", "--operation", "claim-2", success=False)
        self.assertEqual(self.run_cli("next")["action"], "implement")
        self.assertEqual(self.run_cli("next")["owner"], "codex-thread")

    def test_queue_rejects_unknown_or_out_of_order_dependencies(self):
        original = json.loads(self.queue.read_text())
        for dependencies in ([99], [2]):
            with self.subTest(dependencies=dependencies):
                queue = json.loads(json.dumps(original))
                queue["issues"][0]["dependencies"] = dependencies
                write(self.queue, queue)
                result = self.run_cli("init", self.queue, success=False)
                self.assertIn("topologically ordered", result.stderr)
                self.assertFalse(self.state.exists())

    def test_unresolved_restored_dependencies_block_without_an_active_writer(self):
        self.run_cli("init", self.queue)
        state = self.run_cli("show")
        # A resumed snapshot may lack prerequisite work. Absence is not proof
        # of completion; the public CLI must fail closed even without a writer.
        state["queue"] = [state["queue"][1]]
        write(self.state, state)
        self.assertIsNone(state["active"])
        self.assertEqual(self.run_cli("next")["action"], "blocked")
        self.run_cli("claim", "--issue", 2, "--owner", "codex-thread", "--operation", "blocked", success=False)
        self.assertIsNone(self.run_cli("show")["active"])
        state["queue"].append(dict(issue=3, title="feat(web): independent outcome", dependencies=[]))
        write(self.state, state)
        self.assertEqual(self.run_cli("next")["issue"], 3)

    def test_invalid_queue_title_is_rejected_without_creating_state(self):
        queue = json.loads(self.queue.read_text())
        queue["issues"][0]["title"] = "Unnamed work"
        write(self.queue, queue)
        self.run_cli("init", self.queue, success=False)
        self.assertFalse(self.state.exists())

    def test_candidate_branch_must_name_the_active_issue(self):
        checkout, path, request = self.candidate()
        for branch in ("main", "chore/issue-2-delivery", "chore/issue-1-Uppercase"):
            with self.subTest(branch=branch):
                subprocess.check_call(["git", "branch", "-m", branch], cwd=checkout)
                result = self.run_cli("candidate", path, "--checkout", checkout,
                                      "--owner", "codex-thread", success=False)
                self.assertIn("type/issue-N", result.stderr)
                self.assertEqual(self.run_cli("next")["action"], "implement")

    def test_pending_review_cannot_be_replaced_after_restart_and_retry_is_durable(self):
        self.run_cli("init", self.queue)
        self.run_cli("claim", "--issue", 1, "--owner", "codex-thread", "--operation", "claim-1")
        # This command is not permission to launch; a pinned candidate is needed.
        self.run_cli("intent", "--kind", "review", "--operation", "review-1", success=False)
        evidence = self.root / "quota.txt"
        evidence.write_text("Session limit reached; resets at 2030-01-01 00:00 UTC")
        self.run_cli("retry", "--at", "2030-01-01T00:00:00+00:00", "--reason", "CLI session limit",
                     "--evidence", evidence)
        action = self.run_cli("next")
        self.assertEqual(action["action"], "wait")
        self.assertEqual(action["reason"], "CLI session limit")

    def test_heartbeat_is_quiet_for_empty_progress_and_unchanged_state_after_restart(self):
        self.assertEqual(self.run_cli("heartbeat")["decision"], "DONT_NOTIFY")
        self.assertFalse(self.state.exists())
        checkout, path, request = self.candidate()
        self.assertEqual(self.run_cli("heartbeat")["decision"], "DONT_NOTIFY")
        self.run_cli("candidate", path, "--checkout", checkout, "--owner", "codex-thread")
        self.run_cli("intent", "--kind", "review", "--operation", "review-1")
        revision = self.run_cli("show")["revision"]
        self.assertEqual(self.run_cli("heartbeat")["decision"], "DONT_NOTIFY")
        self.assertEqual(self.run_cli("show")["revision"], revision)
        self.run_cli("review", self.review_receipt(request, "CHANGES_REQUIRED"))
        observed = self.run_cli("heartbeat")
        self.assertEqual(observed["decision"], "NOTIFY")
        self.assertIn("review_failed", observed["changes"])
        # Every run_cli call is a fresh process reading the persisted observation.
        self.assertEqual(self.run_cli("heartbeat")["decision"], "DONT_NOTIFY")

    def test_heartbeat_first_observation_baselines_historical_failure(self):
        checkout, path, request = self.candidate()
        self.run_cli("candidate", path, "--checkout", checkout, "--owner", "codex-thread")
        self.run_cli("intent", "--kind", "review", "--operation", "review-1")
        self.run_cli("review", self.review_receipt(request, "CHANGES_REQUIRED"))
        self.assertEqual(self.run_cli("heartbeat")["decision"], "DONT_NOTIFY")
        self.assertEqual(self.run_cli("heartbeat")["decision"], "DONT_NOTIFY")

    def test_heartbeat_reports_new_closure_completion_and_blocked_state_once(self):
        self.run_cli("init", self.queue)
        self.assertEqual(self.run_cli("heartbeat")["decision"], "DONT_NOTIFY")
        state = self.run_cli("show")
        # Durable snapshots are the input boundary, not a hidden test oracle.
        state["queue"] = [state["queue"][1]]
        write(self.state, state)
        self.assertIn("needs_attention", self.run_cli("heartbeat")["changes"])
        self.assertEqual(self.run_cli("heartbeat")["decision"], "DONT_NOTIFY")
        state = self.run_cli("show")
        state["completed"] = {"2": dict(closed=True, issue=2, head="a" * 40)}
        write(self.state, state)
        observed = self.run_cli("heartbeat")
        self.assertEqual(observed["decision"], "NOTIFY")
        self.assertEqual(observed["completed_issues"], [2])
        self.assertEqual(observed["changes"], ["issue_completed", "queue_completed"])
        revision = self.run_cli("show")["revision"]
        self.assertEqual(self.run_cli("heartbeat")["decision"], "DONT_NOTIFY")
        self.assertEqual(self.run_cli("show")["revision"], revision)

    def test_changed_local_transfer_diagnostics_do_not_resolve_pending_review(self):
        checkout, path, request = self.candidate()
        self.run_cli("candidate", path, "--checkout", checkout, "--owner", "codex-thread")
        self.run_cli("intent", "--kind", "review", "--operation", "review-1")
        folder = self.review_receipt(request)
        collection = json.loads((folder / "collection.json").read_text())
        log = folder.with_name(folder.name + ".transfer.log")
        log.write_text("original transfer diagnostics")
        collection["local_transfer"] = dict(log=log.name, sha256=files_index(log.parent, [log.name])[log.name])
        write(folder / "collection.json", collection)
        for altered in ({key: value for key, value in collection.items() if key != "local_transfer"},
                        {**collection, "local_transfer": None}):
            write(folder / "collection.json", altered)
            self.run_cli("review", folder, success=False)
            self.assertEqual(self.run_cli("next")["action"], "reconcile")
        write(folder / "collection.json", collection)
        log.write_text("changed diagnostics")
        result = self.run_cli("review", folder, success=False)
        self.assertIn("Changed evidence", result.stderr)
        self.assertEqual(self.run_cli("next")["action"], "reconcile")
        log.write_text("original transfer diagnostics")
        blocked = checkout / "local/delivery/cleanup-blocked.json"
        blocked.parent.mkdir(parents=True)
        write(blocked, dict(error="fixture cleanup uncertainty"))
        self.run_cli("review", folder, success=False)
        self.assertEqual(self.run_cli("next")["action"], "reconcile")
        blocked.unlink()  # Fixture has no process; production requires retained stop proof.
        self.run_cli("review", folder)
        receipt = self.run_cli("show")["active"]["opus_receipt"]
        self.assertEqual(receipt["collection_digest"], digest(collection))

    def test_revision_conflict_does_not_acquire_a_writer(self):
        self.run_cli("init", self.queue)
        result = subprocess.run([sys.executable, str(SCRIPT), "--config", str(self.config), "--state", str(self.state),
                                 "--revision", "0", "claim", "--issue", "1", "--owner", "new", "--operation", "late"],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.run_cli("next")["action"], "claim")

    def test_dirty_and_wrong_owner_candidates_are_rejected_and_launch_intent_survives(self):
        checkout, path, request = self.candidate()
        (checkout / "source.txt").write_text("uncommitted")
        self.run_cli("candidate", path, "--checkout", checkout, "--owner", "codex-thread", success=False)
        (checkout / "source.txt").write_text("candidate")
        self.run_cli("candidate", path, "--checkout", checkout, "--owner", "another", success=False)
        self.run_cli("candidate", path, "--checkout", checkout, "--owner", "codex-thread")
        self.run_cli("intent", "--kind", "review", "--operation", "review-1")
        self.assertEqual(self.run_cli("next")["action"], "reconcile")
        request["round"] = 2
        path.write_text(json.dumps(request))
        self.run_cli("candidate", path, "--checkout", checkout, "--owner", "codex-thread", success=False)
        self.run_cli("intent", "--kind", "review", "--operation", "review-2", success=False)

    def review_receipt(self, request, verdict="PASS", session="opus-session", issue_digest="a" * 64):
        folder = self.root / f"receipt-{request['round']}"
        folder.mkdir()
        report = {k: request[k] for k in IDENTITY}
        report.update(verdict=verdict, standards=dict(status="PASS", summary="Verified standards"),
                      spec=dict(status="PASS", summary="Verified spec"), findings=[],
                      acceptance=[dict(index=1, status="PASS", evidence="checks.log")])
        evidence = dict(request_digest=digest(request), issue_digest=issue_digest,
                        parent_digest="c" * 64 if request.get("parent_issue") else None,
                        head_before=request["head_sha"], head_after=request["head_sha"],
                        dirty_before="", dirty_after="", process_exit=0, model_error=False,
                        session_id=session, init_session_id=session, skill=dict(name=request["review_skill"], loaded=True, mechanism="Skill", tool_use_id="load", session_id=session, args=request["base_sha"], call_event=1, result_event=2, call_message_id="load-batch"),
                        parent_models=[request["expected_model"]], agents_invoked=["standards-reviewer", "spec-reviewer"],
                        subagent_models={"standards":[request["expected_model"]],"spec":[request["expected_model"]]},
                        checks={"checks":dict(exit_code=0,host="windows",argv=request["checks"][0]["argv"],head_sha=request["head_sha"],log="checks.log")}, axes={})
        (folder / "checks.log").write_text("executed successfully")
        for axis in ("standards", "spec"):
            child = dict(status="PASS",summary="Independent axis complete",findings=[])
            write(folder / f"{axis}.json", child)
            (folder / f"{axis}.txt").write_text("actual child output")
            (folder / f"{axis}-transcript.jsonl").write_text("actual transcript")
            evidence["axes"][axis] = dict(**child, models=[request["expected_model"]], agent_id=axis,tool_use_id=axis, call_event=3, call_message_id="review-batch", session_id=session, run_in_background=False,
                                          completed=True,report=f"{axis}.json",raw_report=f"{axis}.txt",transcript=f"{axis}-transcript.jsonl")
        (folder / "stream.jsonl").write_text("Synthetic parent stream fixture\n")
        write(folder / "request.json", request)
        write(folder / "report.json", report)
        evidence["files"] = files_index(folder, [p.name for p in folder.iterdir()])
        write(folder / "evidence.json", evidence)
        status = dict(run_id=run_id(request),stage="completed",verdict=verdict,request_digest=digest(request),finished=1,worker_alive=False,model_alive=False)
        write(folder / "status.json", status)
        log = folder.with_name(folder.name + ".transfer.log")
        log.write_text("Synthetic transfer diagnostics")
        write(folder / "collection.json", dict(request_digest=digest(request),status=status,
              local_transfer=dict(log=log.name, sha256=files_index(log.parent, [log.name])[log.name])))
        return folder

    def test_opus_without_codex_cannot_merge_and_missing_or_old_receipts_cannot_pass(self):
        checkout, path, request = self.candidate()
        self.run_cli("candidate", path, "--checkout", checkout, "--owner", "codex-thread")
        self.run_cli("intent", "--kind", "review", "--operation", "review-1")
        folder = self.review_receipt(request)
        self.run_cli("review", folder)
        self.assertEqual(self.run_cli("next")["action"], "codex-acceptance")
        acceptance = {k:request[k] for k in IDENTITY}
        acceptance.update(request_digest=digest(request),verdict="PASS",findings=[],
                          acceptance=[dict(index=1,status="PASS",evidence="tests executed")])
        receipt = self.root / "codex.json"
        write(receipt, {**acceptance, "head_sha":"0"*40})
        self.run_cli("accept", receipt, "--owner", "codex-thread", success=False)
        write(receipt, acceptance)
        self.run_cli("accept", receipt, "--owner", "codex-thread")
        self.assertEqual(self.run_cli("next")["action"], "merge")
        request["round"] = 2
        write(path, request)
        self.run_cli("candidate", path, "--checkout", checkout, "--owner", "codex-thread")
        self.run_cli("intent", "--kind", "review", "--operation", "review-2")
        self.run_cli("review", folder, success=False)
        self.assertEqual(self.run_cli("next")["action"], "reconcile")

    def test_repair_returns_to_owner_and_model_session_cannot_change(self):
        checkout, path, request = self.candidate()
        self.run_cli("candidate", path, "--checkout", checkout, "--owner", "codex-thread")
        self.run_cli("intent", "--kind", "review", "--operation", "review-1")
        self.run_cli("review", self.review_receipt(request, "CHANGES_REQUIRED"))
        action = self.run_cli("next")
        self.assertEqual((action["action"], action["owner"]), ("implement", "codex-thread"))
        request["round"] = 2
        write(path, request)
        self.run_cli("candidate", path, "--checkout", checkout, "--owner", "codex-thread")
        self.run_cli("intent", "--kind", "review", "--operation", "review-2")
        self.run_cli("review", self.review_receipt(request, session="replacement-session"), success=False)
        self.assertEqual(self.run_cli("next")["action"], "reconcile")

    def test_merge_recovery_keeps_intent_until_finish_proves_closure(self):
        import coordinator

        checkout, path, request = self.candidate()
        self.run_cli("candidate", path, "--checkout", checkout, "--owner", "codex-thread")
        self.run_cli("intent", "--kind", "review", "--operation", "review-1")
        self.run_cli("review", self.review_receipt(request))
        acceptance = {key: request[key] for key in IDENTITY}
        acceptance.update(request_digest=digest(request), verdict="PASS", findings=[],
                          acceptance=[dict(index=1, status="PASS", evidence="checks executed")])
        receipt = self.root / "codex.json"
        write(receipt, acceptance)
        self.run_cli("accept", receipt, "--owner", "codex-thread")
        argv = [str(SCRIPT), "--config", str(self.config), "--state", str(self.state), "merge", "--issue", "1"]
        # The finisher owns the external GitHub mutation seam. Its unknown outcome
        # must leave the CLI's durable intent, including across a fresh invocation.
        with patch.object(sys, "argv", argv), patch("finish_delivery.finish", side_effect=RuntimeError("unknown send")):
            with self.assertRaisesRegex(RuntimeError, "unknown send"):
                coordinator.main()
        self.assertEqual(self.run_cli("next")["action"], "reconcile")
        closure = dict(closed=True, issue=1, head=request["head_sha"])
        def recovered_finish(*args, reconcile_operation=None):
            self.assertEqual(reconcile_operation, "merge")
            state = json.loads(self.state.read_text())
            self.assertEqual(state["active"]["pending"]["request_digest"], digest(request))
            return closure
        with patch.object(sys, "argv", argv + ["--reconcile-operation", "merge"]), \
                patch("finish_delivery.finish", side_effect=recovered_finish), contextlib.redirect_stdout(io.StringIO()):
            coordinator.main()
        self.assertEqual(self.run_cli("next")["issue"], 2)
        # This historical fixture has no target branch; cached completion alone
        # cannot authorize another successful merge readback.
        rejected = self.run_cli("merge", "--issue", 1, success=False)
        self.assertIn("target branch", rejected.stderr)

    def test_fable_is_separate_and_cannot_replace_opus_consensus(self):
        checkout, path, request = self.candidate()
        self.run_cli("candidate", path, "--checkout", checkout, "--owner", "codex-thread")
        self.run_cli("intent", "--kind", "review", "--operation", "review-1")
        self.run_cli("review", self.review_receipt(request, "CHANGES_REQUIRED"))
        fable = {**request, "round":2,"review_model":"claude-fable-5-1","expected_model":"claude-fable-5-1"}
        write(path, fable)
        self.run_cli("candidate", path, "--checkout", checkout, "--owner", "codex-thread",
                     "--escalation-reason", "Resolve durable recovery contract")
        self.run_cli("intent", "--kind", "review", "--operation", "fable-2")
        self.run_cli("review", self.review_receipt(fable, session="fable-session"))
        state = self.run_cli("show")
        self.assertEqual(state["active"]["sessions"], {"opus":"opus-session","fable":"fable-session"})
        self.assertEqual(self.run_cli("next")["action"], "review-retry")

    def assert_fable_context_revalidation(self, change=None):
        checkout, path, request = self.candidate()
        if change == "upstream":
            request.update(merge_method="merge", upstream_sha=request["base_sha"])
            write(path, request)
        self.run_cli("candidate", path, "--checkout", checkout, "--owner", "codex-thread")
        self.run_cli("intent", "--kind", "review", "--operation", "opus-1")
        self.run_cli("review", self.review_receipt(request, "CHANGES_REQUIRED"))
        fable = {**request, "round": 2, "review_model": "claude-fable-5-1", "expected_model": "claude-fable-5-1"}
        write(path, fable)
        self.run_cli("candidate", path, "--checkout", checkout, "--owner", "codex-thread", "--escalation-reason", "Discuss recovery")
        self.run_cli("intent", "--kind", "review", "--operation", "fable-2")
        self.run_cli("review", self.review_receipt(fable, session="fable-session"))
        request["round"] = 3
        issue_digest = "a" * 64
        if change == "criteria":
            request["criteria"] = ["Persist and recover after restart"]
        elif change == "checks":
            request["checks"] = [dict(name="checks", host="windows", argv=["new-check"], timeout=10)]
        elif change == "parent":
            request["parent_issue"] = 2
        elif change == "spec":
            issue_digest = "b" * 64
        elif change == "merge_method":
            request.update(merge_method="merge", upstream_sha=request["base_sha"])
        elif change == "upstream":
            request["upstream_sha"] = request["head_sha"]
        write(path, request)
        self.run_cli("candidate", path, "--checkout", checkout, "--owner", "codex-thread")
        self.run_cli("intent", "--kind", "review", "--operation", "opus-3")
        self.run_cli("review", self.review_receipt(request, issue_digest=issue_digest))
        acceptance = {key: request[key] for key in IDENTITY}
        acceptance.update(request_digest=digest(request), verdict="PASS", findings=[],
                          acceptance=[dict(index=1, status="PASS", evidence="same candidate reviewed")])
        receipt = self.root / "codex.json"
        write(receipt, acceptance)
        self.run_cli("accept", receipt, "--owner", "codex-thread")
        self.assertEqual(self.run_cli("next")["action"], "fable-review" if change else "merge")
        if change:
            fable = {**request, "round": 4, "review_model": "claude-fable-5-1", "expected_model": "claude-fable-5-1"}
            write(path, fable)
            self.run_cli("candidate", path, "--checkout", checkout, "--owner", "codex-thread", "--escalation-reason", "Recheck current context")
            self.run_cli("intent", "--kind", "review", "--operation", "fable-4")
            self.run_cli("review", self.review_receipt(fable, session="fable-session", issue_digest=issue_digest))
            self.assertEqual(self.run_cli("next")["action"], "merge")

    def test_fable_does_not_accept_replacement_criteria_at_the_same_head(self):
        self.assert_fable_context_revalidation("criteria")

    def test_fable_does_not_accept_a_changed_live_spec_at_the_same_head(self):
        self.assert_fable_context_revalidation("spec")

    def test_fable_can_reuse_the_same_context_across_model_and_round_changes(self):
        self.assert_fable_context_revalidation()

    def test_fable_does_not_accept_replacement_check_commands(self):
        self.assert_fable_context_revalidation("checks")

    def test_fable_does_not_accept_replacement_parent_specifications(self):
        self.assert_fable_context_revalidation("parent")

    def test_fable_does_not_accept_a_changed_merge_method(self):
        self.assert_fable_context_revalidation("merge_method")

    def test_fable_does_not_accept_a_changed_upstream(self):
        self.assert_fable_context_revalidation("upstream")

    def test_candidate_requires_frozen_upstream_ancestry(self):
        checkout, path, request = self.candidate()
        tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=checkout, text=True).strip()
        upstream = subprocess.check_output(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "-c", "commit.gpgsign=false", "commit-tree", tree, "-m", "unrelated upstream"], cwd=checkout, text=True).strip()
        request.update(merge_method="merge", upstream_sha=upstream)
        write(path, request)
        state_before = self.state.read_bytes()
        rejected = self.run_cli("candidate", path, "--checkout", checkout, "--owner", "codex-thread", success=False)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertEqual(self.state.read_bytes(), state_before)

    def test_missing_actual_specification_digest_never_accepts_a_review(self):
        checkout, path, request = self.candidate()
        self.run_cli("candidate", path, "--checkout", checkout, "--owner", "codex-thread")
        self.run_cli("intent", "--kind", "review", "--operation", "review-1")
        self.run_cli("review", self.review_receipt(request, issue_digest=None), success=False)
        self.assertEqual(self.run_cli("next")["action"], "reconcile")

    def test_concurrent_claims_cannot_create_two_implementation_owners(self):
        self.run_cli("init", self.queue)
        base = [sys.executable, str(SCRIPT), "--config", str(self.config), "--state", str(self.state),
                "claim", "--issue", "1"]
        processes = [subprocess.Popen(base + ["--owner", owner, "--operation", owner],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                     for owner in ("writer-a", "writer-b")]
        for process in processes:
            process.communicate(timeout=15)
        self.assertEqual(sum(p.returncode == 0 for p in processes), 1)
        self.assertIn(self.run_cli("next")["owner"], ("writer-a", "writer-b"))


if __name__ == "__main__":
    unittest.main()
