"""Acceptance gate regressions using synthetic receipts; never calls Claude/GitHub."""

import copy
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from delivery import CleanupError, execute_checks, files_index, live_candidate, premerge, terminate_tree, write
from review_gate import IDENTITY, digest, gate, spec_digest, validate_request, verify_files, repository_matches
from review_protocol import axis_receipts, session_arguments, validate_session_model, skill_receipt


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.config = dict(repo="test/project", merge_method="squash", review_skill="matt-code-review", actual_models={"opus":"claude-opus-5-5", "claude-fable-5-1":"claude-fable-5-1"})
        self.request = dict(repo="test/project", issue=51, parent_issue=None, pr=100, round=1,
                            base_sha="a"*40, head_sha="b"*40, target_base_sha="a"*40,
                            target_branch="main", criteria=["A complete requirement"],
                            expected_model="claude-opus-5-5", review_skill="matt-code-review",
                            checks=[dict(name="check", host="windows", argv=["check", "--all"], timeout=10)])
        self.report = {k: self.request[k] for k in IDENTITY}
        self.report.update(standards=dict(status="PASS", summary="Standards checked"),
                           spec=dict(status="PASS", summary="Spec checked"), findings=[], verdict="PASS",
                           acceptance=[dict(index=1, status="PASS", evidence="windows-check.log")])
        self.evidence = dict(request_digest=digest(self.request), head_before="b"*40, head_after="b"*40,
                             dirty_before="", dirty_after="", process_exit=0, model_error=False,
                             session_id="session", init_session_id="session", skill=dict(name="matt-code-review", loaded=True, mechanism="Skill", tool_use_id="load", session_id="session", args=self.request["base_sha"], call_event=1, result_event=2, call_message_id="load-batch"),
                             parent_models=["claude-opus-5-5"], agents_invoked=["standards-reviewer", "spec-reviewer"],
                             subagent_models={"a":["claude-opus-5-5"], "b":["claude-opus-5-5"]},
                             checks={"check":dict(exit_code=0, host="windows", argv=["check", "--all"], head_sha="b"*40,
                                                  log="windows-check.log")}, files={"windows-check.log":"fake", "stream.jsonl":"fake"})
        self.evidence["axes"] = {}
        for axis in ("standards", "spec"):
            self.evidence["axes"][axis] = dict(tool_use_id=axis, agent_id=axis, completed=True, call_event=3, call_message_id="review-batch", session_id="session", run_in_background=False,
                models=["claude-opus-5-5"], status="PASS", summary="Independent full report", findings=[],
                report=f"{axis}-child.json", raw_report=f"{axis}-child.txt", transcript=f"{axis}-transcript.jsonl")
            self.evidence["files"].update({f"{axis}-child.json":"fake", f"{axis}-child.txt":"fake", f"{axis}-transcript.jsonl":"fake"})

    def test_gate_requires_actual_skill_before_one_parent_tool_batch(self):
        def tool(identifier, name, data, batch):
            return dict(type="assistant", session_id="session", parent_tool_use_id=None, message=dict(id=batch,
                content=[dict(type="tool_use", id=identifier, name=name, input=data)]))

        def result(identifier, text, **extra):
            return dict(type="user", session_id="session", parent_tool_use_id=None, message=dict(content=[
                dict(type="tool_result", tool_use_id=identifier, content=text, **extra)]))

        skill = tool("load", "Skill", dict(skill="matt-code-review", args=self.request["base_sha"]), "load-batch")
        loaded = result("load", "Base directory for this skill: /skills/matt-code-review\nReview standards")
        standards = tool("standards", "Task", dict(subagent_type="standards-reviewer", run_in_background=False), "review-batch")
        spec = tool("spec", "Agent", dict(subagent_type="spec-reviewer", run_in_background=False), "review-batch")
        child = lambda axis: dict(axis=axis, status="PASS", summary="Independent review", findings=[])
        standards_done = result("standards", json.dumps(child("standards")) + "\nagentId: standards")
        spec_done = result("spec", json.dumps(child("spec")) + "\nagentId: spec")
        # The actual CLI can split one message's calls across events and interleave
        # child progress/results. message.id, not the stream row, defines a batch.
        valid = [skill, loaded, standards, standards_done, spec, spec_done]
        variants = {
            "split-events-same-parent-message": (valid, True),
            "missing-skill": (valid[2:], False),
            "failed-skill": ([skill, result("load", "disabled", is_error=True), *valid[2:]], False),
            "late-skill": ([*valid[2:], skill, loaded], False),
            "skill-before-init": ([skill, loaded, dict(type="system", subtype="init", session_id="session"), *valid[2:]], False),
            "slash-only": ([dict(type="user", session_id="session", message=dict(content="<command-name>/matt-code-review</command-name> Base directory for this skill: /skills/review")), *valid[2:]], False),
        }
        for name in ("serial-batches", "background-axis", "missing-message-id", "wrong-skill-base", "nested-skill", "nested-axis", "old-session-skill", "old-session-axis", "skill-and-axes-one-batch"):
            records = copy.deepcopy(valid)
            if name == "serial-batches":
                records[4]["message"]["id"] = "later-review-batch"
            elif name == "background-axis":
                records[4]["message"]["content"][0]["input"]["run_in_background"] = True
            elif name == "missing-message-id":
                records[4]["message"].pop("id")
            elif name == "wrong-skill-base":
                records[0]["message"]["content"][0]["input"]["args"] = "another-base"
            elif name == "nested-skill":
                records[0]["parent_tool_use_id"] = records[1]["parent_tool_use_id"] = "outer-child"
            elif name == "nested-axis":
                records[4]["parent_tool_use_id"] = records[5]["parent_tool_use_id"] = "outer-child"
            elif name == "skill-and-axes-one-batch":
                records[0]["message"]["id"] = "review-batch"
            elif name == "old-session-skill":
                records[0]["session_id"] = records[1]["session_id"] = "previous-session"
            elif name == "old-session-axis":
                records[4]["session_id"] = records[5]["session_id"] = "previous-session"
            variants[name] = (records, False)
        for name, (records, passes) in variants.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for axis in ("standards", "spec"):
                    # JSONL uses compact single-line records.
                    (root / f"agent-{axis}.jsonl").write_text(json.dumps(dict(type="assistant", message=dict(model="claude-opus-5-5"))) + "\n")
                if not any(event.get("subtype") == "init" for event in records):
                    records = [dict(type="system", subtype="init", session_id="session"), *records]
                evidence = copy.deepcopy(self.evidence)
                evidence["skill"] = skill_receipt(records, self.request["review_skill"])
                evidence["axes"] = axis_receipts(records, root, root)
                (root / "stream.jsonl").write_text("\n".join(map(json.dumps, records)) + "\n")
                evidence["files"].update(files_index(root, [p.name for p in root.iterdir()]))
                problems = gate(self.request, self.report, evidence)
                if passes:
                    self.assertEqual(problems, [])
                    self.assertEqual(evidence["axes"]["standards"]["call_message_id"], evidence["axes"]["spec"]["call_message_id"])
                else:
                    self.assertTrue(problems, "Invalid parent protocol must not authorize merge")

    def test_complete_evidence(self):
        validate_request(self.request, self.config)
        self.assertEqual(gate(self.request, self.report, self.evidence), [])

    def test_fable_request_requires_actual_fable_parent_and_both_axes(self):
        request = {**self.request, "review_model": "claude-fable-5-1", "expected_model":"claude-fable-5-1"}
        validate_request(request, self.config)
        evidence = copy.deepcopy(self.evidence)
        evidence["request_digest"] = digest(request)
        # Relabelling an Opus receipt does not make it Fable evidence.
        self.assertTrue(gate(request, self.report, evidence))
        evidence["parent_models"] = ["claude-fable-5-1"]
        evidence["subagent_models"] = {"a": ["claude-fable-5-1"], "b": ["claude-fable-5-1"]}
        for axis in evidence["axes"].values():
            axis["models"] = ["claude-fable-5-1"]
        self.assertEqual(gate(request, self.report, evidence), [])
        for wrong in ("claude-opus-5-5", "claude-sonnet", "claude-fable-5-2", "fable", ""):
            for location in ("parent", "transcript", "axis"):
                with self.subTest(wrong=wrong, location=location):
                    changed = copy.deepcopy(evidence)
                    if location == "parent":
                        changed["parent_models"].append(wrong)
                    elif location == "transcript":
                        changed["subagent_models"]["b"] = [wrong]
                    else:
                        changed["axes"]["spec"]["models"] = [wrong]
                    self.assertTrue(gate(request, self.report, changed))
        self.assertTrue(gate(self.request, self.report, evidence))

    def test_unsupported_review_models_rejected(self):
        for model in (None, "", "fable", "claude-fable-5-2", "sonnet", [], {}):
            with self.subTest(model=model), self.assertRaises(ValueError):
                validate_request({**self.request, "review_model": model}, self.config)

    def test_session_model_change_requires_explicit_reconciliation(self):
        validate_session_model(None, "claude-fable-5-1")
        validate_session_model({"session_id": "old"}, "opus")
        previous = {"session_id": "fable", "review_model": "claude-fable-5-1"}
        validate_session_model(previous, "claude-fable-5-1")
        for old, requested in (({"session_id": "old"}, "claude-fable-5-1"), (previous, "opus")):
            before = copy.deepcopy(old)
            with self.assertRaises(ValueError):
                validate_session_model(old, requested)
            self.assertEqual(old, before)

    def test_malformed_or_cross_repository_request(self):
        for change in (dict(repo="wrong/repo"), dict(head_sha="main"), dict(issue=0), dict(criteria=[]),
                       dict(checks=[]), dict(checks=[dict(name="../escape", host="linux", argv=["true"], timeout=1)])):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_request({**self.request, **change}, self.config)

    def test_review_checkout_origin_requires_the_exact_github_repository(self):
        for remote in ("https://github.com/test/project.git", "git@github.com:test/project.git"):
            self.assertTrue(repository_matches(remote, "test/project"))
        for remote in ("https://other.invalid/test/project.git", "https://github.com/not-test/project.git", "https://github.com/extra/test/project.git"):
            self.assertFalse(repository_matches(remote, "test/project"))

    def test_wrong_host_old_head_and_changed_command_rejected(self):
        for change in (dict(host="linux"), dict(head_sha="c"*40), dict(argv=["different"]), dict(exit_code=1), dict(log="absent.log")):
            e = copy.deepcopy(self.evidence)
            e["checks"]["check"].update(change)
            self.assertTrue(gate(self.request, self.report, e))

    def test_stale_dirty_partial_or_wrong_model_rejected(self):
        for change in (dict(head_after="c"*40), dict(dirty_before=" M code"), dict(dirty_after="?? data"),
                       dict(request_digest="changed"), dict(checks={}), dict(process_exit=1), dict(model_error=True),
                       dict(parent_models=["claude-sonnet"]), dict(agents_invoked=["standards-reviewer"]),
                       dict(subagent_models={"a":["claude-opus"], "b":["claude-sonnet"]})):
            with self.subTest(change=change):
                self.assertTrue(gate(self.request, self.report, {**self.evidence, **change}))

    def test_skill_session_and_actual_model_are_required(self):
        for change in (dict(skill={}), dict(skill=dict(name="other", loaded=True)),
                       dict(init_session_id="another-session"), dict(session_id=None),
                       dict(parent_models=["not-opus"]), dict(parent_models=["claude-opus-5-4"])):
            with self.subTest(change=change):
                self.assertTrue(gate(self.request, self.report, {**self.evidence, **change}))

    def test_old_or_incomplete_report_rejected(self):
        for change in (dict(repo="wrong/repo"), dict(head_sha="c"*40), dict(target_branch="wrong"), dict(acceptance=[]),
                       dict(acceptance=[dict(index=1,status="INSUFFICIENT",evidence="missing")]),
                       dict(standards=dict(status="FAIL", summary="failure")), dict(findings=[dict(blocking=True)]),
                       dict(verdict="CHANGES_REQUIRED")):
            with self.subTest(change=change):
                self.assertTrue(gate(self.request, {**self.report, **change}, self.evidence))
        self.assertTrue(gate(self.request, None, self.evidence))

    def test_tampered_missing_and_escaped_log(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/"log").write_text("real output")
            index=files_index(root,["log"])
            self.assertEqual(verify_files(root,index),[])
            (root/"log").write_text("different output")
            self.assertTrue(verify_files(root,index))
            self.assertTrue(verify_files(root,{"../outside":"hash"}))
            self.assertTrue(verify_files(root,{"missing":"hash"}))

    def test_live_candidate_changed_base_head_or_branch(self):
        pr = dict(headRefOid="b"*40, baseRefOid="a"*40, baseRefName="main",
                  headRefName=f"chore/issue-{self.request['issue']}-delivery", title="chore(delivery): outcome")
        issue = dict(number=self.request["issue"], title=pr["title"])
        with patch("delivery.gh", side_effect=[pr, issue]):
            self.assertEqual(live_candidate(self.config, self.request), pr)
        for change in (dict(headRefOid="c"*40), dict(baseRefOid="c"*40), dict(baseRefName="wrong")):
            with patch("delivery.gh", return_value={**pr, **change}), self.assertRaises(RuntimeError):
                live_candidate(self.config, self.request)

    def test_premerge_rejects_changed_spec_or_failed_ci(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/"windows-check.log").write_text("real output")
            for axis in ("standards", "spec"):
                (root/f"{axis}-child.json").write_text("independent report")
                (root/f"{axis}-child.txt").write_text("raw independent report")
                (root/f"{axis}-transcript.jsonl").write_text("actual transcript")
            evidence=copy.deepcopy(self.evidence)
            (root / "stream.jsonl").write_text("Synthetic parent stream fixture\n")
            evidence["files"]=files_index(root,list(evidence["files"]))
            evidence["issue_digest"]=spec_digest(dict(title="old",body="req",comments=[]))
            for name,value in (("request",self.request),("report",self.report),("evidence",evidence),("status",dict(verdict="PASS"))):
                write(root/f"{name}.json",value)
            with patch("delivery.gh",return_value=dict(title="changed",body="req",comments=[])), self.assertRaises(RuntimeError):
                premerge(self.config,root)
            pr=dict(state="OPEN",isDraft=False,mergeable="MERGEABLE",statusCheckRollup=[dict(__typename="CheckRun",status="IN_PROGRESS")])
            with patch("delivery.gh",return_value=dict(title="old",body="req",comments=[])), patch("delivery.live_candidate",return_value=pr), self.assertRaises(RuntimeError):
                premerge(self.config,root)

    def test_child_completion_and_axis_identity_required(self):
        for change in (dict(completed=False),dict(status="FAIL"),dict(findings=[dict(blocking=True)]),
                       dict(agent_id="standards"),dict(models=["claude-sonnet"]),dict(report="absent"),dict(transcript="absent")):
            evidence=copy.deepcopy(self.evidence)
            evidence["axes"]["spec"].update(change)
            self.assertTrue(gate(self.request,self.report,evidence))

    def test_axis_collector_binds_foreground_result_to_transcript(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            child=dict(axis="spec",status="PASS",summary="Complete independent report",findings=[])
            (root/"agent-testid.jsonl").write_text(json.dumps(dict(type="assistant",message=dict(model="claude-opus-test"))))
            call=dict(type="tool_use",id="call",name="Agent",input=dict(subagent_type="spec-reviewer"))
            result=dict(type="tool_result",tool_use_id="call",content=json.dumps(child)+"\nagentId: testid")
            records=[dict(type="system", subtype="init", session_id="current"),
                     dict(type="assistant", session_id="current", message=dict(id="batch",content=[call])),
                     dict(type="user", session_id="current", message=dict(content=[result]))]
            axes=axis_receipts(records,root,root)
            self.assertEqual(axes["spec"]["agent_id"],"testid")
            self.assertEqual(axes["spec"]["tool_use_id"],"call")
            self.assertNotIn("standards",axes)
            retry=dict(type="tool_use",id="retry",name="Agent",input=dict(subagent_type="spec-reviewer"))
            self.assertEqual(axis_receipts(records+[dict(type="assistant", session_id="current", message=dict(id="retry-batch",content=[retry]))],root,root),{})
            result["is_error"]=True
            self.assertEqual(axis_receipts(records,root,root),{})
            result["is_error"]=False
            call["input"]["run_in_background"]=True
            self.assertEqual(axis_receipts(records,root,root),{})
            self.assertEqual(axis_receipts(records[:1],root,root),{})

    def test_reserved_session_is_resumed_only_when_transcript_exists(self):
        with tempfile.TemporaryDirectory() as temp:
            transcript=Path(temp)/"session.jsonl"
            self.assertEqual(session_arguments("id",transcript),["--session-id","id"])
            transcript.write_text("session record")
            self.assertEqual(session_arguments("id",transcript),["--resume","id"])

    def test_timeout_stops_descendant_process(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            marker=root/"late-write"
            child=f"import time,pathlib; time.sleep(2); pathlib.Path({str(marker)!r}).write_text('leak')"
            parent=f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(10)"
            request=dict(head_sha="b"*40,checks=[dict(name="tree",host="windows",argv=[sys.executable,"-c",parent],timeout=1)])
            result=execute_checks(request,"windows",root,root)
            self.assertEqual(result["tree"]["exit_code"],124)
            time.sleep(1.5)
            self.assertFalse(marker.exists(),"Timed-out command left a writer alive")

    def test_cleanup_failure_is_explicit_and_wait_is_bounded(self):
        process=Mock(pid=123)
        with patch("delivery.os.name","nt"), patch("delivery.subprocess.run",return_value=Mock(returncode=1,stderr="denied")):
            with self.assertRaises(CleanupError):
                terminate_tree(process)
            process.wait.assert_not_called()
        process.wait.side_effect=subprocess.TimeoutExpired("child",10)
        with patch("delivery.os.name","nt"), patch("delivery.subprocess.run",return_value=Mock(returncode=0)):
            with self.assertRaises(CleanupError):
                terminate_tree(process)
            process.wait.assert_called_once_with(timeout=10)
        with patch("delivery.os.name","posix"), patch("delivery.signal.SIGKILL",9,create=True), patch("delivery.os.killpg",create=True,side_effect=PermissionError("denied")):
            with self.assertRaises(CleanupError):
                terminate_tree(process)

    @unittest.skipIf(os.name == "nt", "Linux OS lock inheritance")
    def test_child_retains_worker_lock_after_parent_handle_closes(self):
        import fcntl
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"worker.lock"
            owner=path.open("a")
            fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
            child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(10)"],
                                   pass_fds=(owner.fileno(),),start_new_session=True)
            owner.close()
            try:
                with path.open("a") as contender:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(contender,fcntl.LOCK_EX|fcntl.LOCK_NB)
            finally:
                terminate_tree(child)


if __name__ == "__main__":
    unittest.main()
