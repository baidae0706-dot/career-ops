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

    def review_receipt(self, request, verdict="PASS", session="opus-session"):
        folder = self.root / f"receipt-{request['round']}"
        folder.mkdir()
        report = {k: request[k] for k in IDENTITY}
        report.update(verdict=verdict, standards=dict(status="PASS", summary="Verified standards"),
                      spec=dict(status="PASS", summary="Verified spec"), findings=[],
                      acceptance=[dict(index=1, status="PASS", evidence="checks.log")])
        evidence = dict(request_digest=digest(request), head_before=request["head_sha"], head_after=request["head_sha"],
                        dirty_before="", dirty_after="", process_exit=0, model_error=False,
                        session_id=session, init_session_id=session, skill=dict(name=request["review_skill"], loaded=True),
                        parent_models=[request["expected_model"]], agents_invoked=["standards-reviewer", "spec-reviewer"],
                        subagent_models={"standards":[request["expected_model"]],"spec":[request["expected_model"]]},
                        checks={"checks":dict(exit_code=0,host="windows",argv=["check"],head_sha=request["head_sha"],log="checks.log")}, axes={})
        (folder / "checks.log").write_text("executed successfully")
        for axis in ("standards", "spec"):
            child = dict(status="PASS",summary="Independent axis complete",findings=[])
            write(folder / f"{axis}.json", child)
            (folder / f"{axis}.txt").write_text("actual child output")
            (folder / f"{axis}-transcript.jsonl").write_text("actual transcript")
            evidence["axes"][axis] = dict(**child, models=[request["expected_model"]], agent_id=axis,tool_use_id=axis,
                                          completed=True,report=f"{axis}.json",raw_report=f"{axis}.txt",transcript=f"{axis}-transcript.jsonl")
        write(folder / "request.json", request)
        write(folder / "report.json", report)
        evidence["files"] = files_index(folder, [p.name for p in folder.iterdir()])
        write(folder / "evidence.json", evidence)
        status = dict(run_id=run_id(request),stage="completed",verdict=verdict,request_digest=digest(request),finished=1,worker_alive=False,model_alive=False)
        write(folder / "status.json", status)
        write(folder / "collection.json", dict(request_digest=digest(request),status=status))
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
        self.assertEqual(self.run_cli("merge", "--issue", 1), closure)

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
