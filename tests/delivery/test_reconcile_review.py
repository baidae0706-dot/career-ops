"""Original-run recovery through disk evidence and the OS process/lock boundary."""

import contextlib
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import reconcile_review
from delivery import read, run_id, write
from review_gate import digest, verify_files


BOOT = "11111111-1111-4111-8111-111111111111"
NEW_BOOT = "22222222-2222-4222-8222-222222222222"


def stat_text(pid, start="100", state="S", parent=1, group=1, session=1):
    values = [state, str(parent), str(group), str(session)] + ["0"] * 15 + [start]
    return f"{pid} (a process with spaces) " + " ".join(values)


class ReconcileReviewTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).resolve().parents[3] / ".career-ops-delivery-tests"
        scratch.mkdir(exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        remote_root = self.root.as_posix()
        if os.name == "nt":
            remote_root = remote_root.removeprefix(self.root.drive)
        self.config = dict(repo="example/career", remote_root=remote_root,
                           actual_models={"opus": "claude-opus-5-5"}, review_skill="matt-code-review")
        self.request = dict(repo=self.config["repo"], issue=1, pr=2, round=1, base_sha="b" * 40,
            head_sha="a" * 40, target_base_sha="b" * 40, target_branch="main",
            review_model="opus", expected_model="claude-opus-5-5", review_skill="matt-code-review",
            criteria=["Recover the original round"],
            checks=[dict(name="syntax", host="linux", argv=["python3", "-V"], timeout=10)])
        self.run = run_id(self.request)
        self.incoming, self.folder = self.root / "incoming" / self.run, self.root / "runs" / self.run
        self.incoming.mkdir(parents=True)
        self.folder.mkdir(parents=True)
        write(self.incoming / "request.json", self.request)
        write(self.incoming / "local-evidence.json", dict(request_digest=digest(self.request), checks={}))
        write(self.incoming / "upload-manifest.json", {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                                       for p in self.incoming.iterdir()})
        write(self.folder / "request.json", self.request)
        write(self.folder / "evidence.json", dict(request_digest=digest(self.request), checks={}))
        self.lock = self.root / "worker.lock"
        self.lock.touch()
        details = self.lock.stat()
        self.uid = os.getuid() if hasattr(os, "getuid") else 0
        self.status = dict(run_id=self.run, request_digest=digest(self.request), stage="model-review",
            pid=900001, pid_start_ticks="100", boot_id=BOOT, worker_uid=self.uid,
            worker_lock=dict(device=details.st_dev, inode=details.st_ino), worker_lock_acquired=True,
            session_id="33333333-3333-4333-8333-333333333333", review_model="opus")
        write(self.folder / "status.json", self.status)
        (self.folder / "stream.jsonl").write_text('{"type":"system","session_id":"original"}\n', encoding="utf-8")
        (self.folder / "stderr.log").write_text("Original incomplete output\n", encoding="utf-8")
        self.proc = self.root / "proc"
        boot_path = self.proc / "sys/kernel/random/boot_id"
        boot_path.parent.mkdir(parents=True)
        boot_path.write_text(BOOT, encoding="utf-8")
        self.lock_busy = False

    @contextlib.contextmanager
    def fake_lock(self, path, expected):
        details = path.stat()
        actual = dict(device=details.st_dev, inode=details.st_ino)
        if self.lock_busy or actual != expected:
            raise reconcile_review.Unverified("Original lock unavailable")
        yield actual

    def call(self):
        original = reconcile_review.process_evidence
        with patch("reconcile_review.original_worker_lock", side_effect=self.fake_lock), \
                patch("reconcile_review.process_evidence", side_effect=lambda state, folder, incoming:
                      original(state, folder, incoming, self.proc, uid=self.uid)):
            return reconcile_review.reconcile(self.config, self.run)

    def add_process(self, pid, **kwargs):
        folder = self.proc / str(pid)
        folder.mkdir()
        (folder / "stat").write_text(stat_text(pid, **kwargs), encoding="utf-8")
        (folder / "fd").mkdir()
        return folder

    def test_stopped_round_seals_insufficient_preserving_session_logs_and_report(self):
        write(self.folder / "report.json", dict(verdict="PASS", findings=[]))
        original = {name: (self.folder / name).read_bytes() for name in ("stream.jsonl", "stderr.log", "report.json")}
        result = self.call()
        self.assertEqual(result["reconciliation"], "sealed")
        self.assertEqual(result["verdict"], "INSUFFICIENT")
        self.assertEqual(result["session_id"], self.status["session_id"])
        self.assertEqual(read(self.folder / "evidence.json")["session_id"], self.status["session_id"])
        self.assertEqual(verify_files(self.folder, read(self.folder / "evidence.json")["files"]), [])
        self.assertEqual({name: (self.folder / name).read_bytes() for name in original}, original)
        receipt = read(self.folder / "reconciliation.json")
        self.assertEqual(receipt["process_evidence"]["processes"]["model"]["start_outcome"], "unknown")
        self.assertEqual(receipt["original_status"], self.status)
        before = {p.name: p.read_bytes() for p in self.folder.iterdir()}
        self.assertEqual(self.call()["reconciliation"], "already-terminal")
        self.assertEqual({p.name: p.read_bytes() for p in self.folder.iterdir()}, before)

    def test_active_worker_or_reused_pid_stays_pending_without_writes(self):
        process = self.add_process(self.status["pid"])
        before = {p.name: p.read_bytes() for p in self.folder.iterdir()}
        self.assertIn("still active", self.call()["reason"])
        (process / "stat").write_text(stat_text(self.status["pid"], start="999"), encoding="utf-8")
        self.assertIn("reused", self.call()["reason"])
        self.assertEqual({p.name: p.read_bytes() for p in self.folder.iterdir()}, before)

    def test_unknown_birth_identity_and_busy_inherited_lock_stay_pending(self):
        self.lock_busy = True
        self.assertEqual(self.call()["reconciliation"], "pending")
        self.lock_busy = False
        self.status.pop("pid_start_ticks")
        write(self.folder / "status.json", self.status)
        self.assertIn("incomplete", self.call()["reason"])
        self.assertFalse((self.folder / "reconciliation.json").exists())

    def test_reboot_proves_old_birth_ended_without_confusing_reused_pid(self):
        (self.proc / "sys/kernel/random/boot_id").write_text(NEW_BOOT, encoding="utf-8")
        self.add_process(self.status["pid"], start="500", group=self.status["pid"])
        result = self.call()
        self.assertEqual(result["reconciliation"], "sealed")
        proof = read(self.folder / "reconciliation.json")["process_evidence"]
        self.assertTrue(proof["boot_changed"])
        self.assertEqual(proof["processes"]["worker"]["state"], "previous_boot_ended")
        self.assertEqual(proof["processes"]["model"]["start_outcome"], "unknown")

    def test_remaining_child_tree_or_log_holder_prevents_sealing(self):
        process = self.add_process(900002, group=self.status["pid"])
        self.assertEqual(self.call()["reconciliation"], "pending")
        (process / "stat").write_text(stat_text(900002), encoding="utf-8")
        descriptor = process / "fd/1"
        descriptor.touch()
        original_stat = Path.stat
        for name in ("stream.jsonl", "linux-syntax.log"):
            log = self.folder / name
            log.touch(exist_ok=True)

            def descriptor_identity(path, *args, **kwargs):
                return original_stat(log if path == descriptor else path, *args, **kwargs)

            with patch.object(Path, "stat", new=descriptor_identity):
                self.assertIn("holds", self.call()["reason"])
        self.assertFalse((self.folder / "reconciliation.json").exists())

    def test_preexisting_unrelated_process_does_not_require_descriptor_access(self):
        process = self.add_process(900002, start="99")
        descriptor = process / "fd/0"
        descriptor.touch()
        original_stat = Path.stat

        def denied_descriptor(path, *args, **kwargs):
            if path == descriptor:
                raise PermissionError(13, "Permission denied", str(path))
            return original_stat(path, *args, **kwargs)

        with patch.object(Path, "stat", new=denied_descriptor):
            result = self.call()
        self.assertEqual(result["reconciliation"], "sealed", result)
        self.assertEqual(result["verdict"], "INSUFFICIENT")
        proof = read(self.folder / "reconciliation.json")["process_evidence"]
        self.assertEqual(proof["excluded_preexisting_processes"], [dict(pid=900002, start_ticks="99")])

    def test_same_later_or_unknown_birth_with_unreadable_descriptors_stays_pending(self):
        process = self.add_process(900002)
        descriptor = process / "fd/0"
        descriptor.touch()
        original_stat = Path.stat

        def denied_descriptor(path, *args, **kwargs):
            if path == descriptor:
                raise PermissionError(13, "Permission denied", str(path))
            return original_stat(path, *args, **kwargs)

        before = {p.name: p.read_bytes() for p in self.folder.iterdir()}
        for start in ("100", "101", "unknown", ""):
            with self.subTest(start=start):
                (process / "stat").write_text(stat_text(900002, start=start), encoding="utf-8")
                with patch.object(Path, "stat", new=denied_descriptor):
                    self.assertEqual(self.call()["reconciliation"], "pending")
        self.assertEqual({p.name: p.read_bytes() for p in self.folder.iterdir()}, before)

    def test_preexisting_process_with_original_tree_relation_stays_pending(self):
        process = self.add_process(900002, start="99")
        for relation in ("parent", "group", "session"):
            with self.subTest(relation=relation):
                (process / "stat").write_text(
                    stat_text(900002, start="99", **{relation: self.status["pid"]}), encoding="utf-8")
                self.assertIn("original worker/model tree", self.call()["reason"])
        self.assertFalse((self.folder / "reconciliation.json").exists())

    def test_unreadable_descriptor_directory_remains_pending_for_possible_child(self):
        process = self.add_process(900002, start="101")
        original_iterdir = Path.iterdir

        def denied_directory(path):
            if path == process / "fd":
                raise PermissionError(13, "Permission denied", str(path))
            return original_iterdir(path)

        with patch.object(Path, "iterdir", new=denied_directory):
            self.assertEqual(self.call()["reconciliation"], "pending")
            (process / "stat").write_text(stat_text(900002, start="99"), encoding="utf-8")
            self.assertEqual(self.call()["reconciliation"], "sealed")

    def test_reboot_proves_original_tree_ended_without_reading_new_boot_descriptors(self):
        (self.proc / "sys/kernel/random/boot_id").write_text(NEW_BOOT, encoding="utf-8")
        process = self.add_process(900002, start="1", group=self.status["pid"])
        original_iterdir = Path.iterdir

        def denied_directory(path):
            if path == process / "fd":
                raise PermissionError(13, "Permission denied", str(path))
            return original_iterdir(path)

        with patch.object(Path, "iterdir", new=denied_directory):
            result = self.call()
        self.assertEqual(result["reconciliation"], "sealed", result)
        self.assertEqual(result["verdict"], "INSUFFICIENT")
        proof = read(self.folder / "reconciliation.json")["process_evidence"]
        self.assertEqual(proof["descriptor_scan"], "not_required_previous_boot_ended")
        self.assertEqual(proof["processes"]["model"]["start_outcome"], "unknown")

    def test_changed_manifest_request_or_lock_cannot_be_recovered(self):
        (self.incoming / "local-evidence.json").write_text("{}", encoding="utf-8")
        self.assertIn("changed", self.call()["reason"])
        self.assertFalse((self.folder / "reconciliation.json").exists())

    def test_unknown_launch_without_worker_status_is_not_called_unstarted(self):
        (self.folder / "status.json").unlink()
        write(self.incoming / "launch-intent.json", dict(run_id=self.run, outcome="unknown"))
        result = self.call()
        self.assertEqual(result["reconciliation"], "pending")
        self.assertIn("unknown", result["reason"])
        self.assertFalse((self.folder / "status.json").exists())

    def initial_status_only(self):
        self.status.update(stage="preparing")
        self.status.pop("session_id")
        self.status.pop("review_model")
        write(self.folder / "status.json", self.status)
        for name in ("request.json", "evidence.json", "stream.jsonl", "stderr.log"):
            (self.folder / name).unlink()

    def test_status_before_request_crash_restores_only_after_lock_and_exit_proof(self):
        self.initial_status_only()
        (self.folder / "request.json.tmp").write_text('{"partial":', encoding="utf-8")
        self.lock_busy = True
        self.assertEqual(self.call()["reconciliation"], "pending")
        self.assertFalse((self.folder / "request.json").exists())
        self.lock_busy = False
        process = self.add_process(self.status["pid"])
        self.assertEqual(self.call()["reconciliation"], "pending")
        self.assertFalse((self.folder / "request.json").exists())
        (process / "stat").write_text(stat_text(self.status["pid"], state="Z"), encoding="utf-8")
        self.assertEqual(self.call()["reconciliation"], "sealed")
        self.assertEqual(read(self.folder / "request.json"), self.request)
        record = read(self.folder / "reconciliation.json")
        self.assertTrue(record["original_request_missing"])
        self.assertEqual(record["preserved_files"], {})
        self.assertEqual(verify_files(self.folder, read(self.folder / "evidence.json")["files"]), [])

    def test_request_restoration_interruption_keeps_original_missing_evidence(self):
        self.initial_status_only()
        original_write = reconcile_review.write
        crashed = False

        def stop_before_request(path, value):
            nonlocal crashed
            if Path(path).resolve() == self.folder / "request.json" and not crashed:
                crashed = True
                raise OSError("Injected interruption after recovery record, before request copy")
            return original_write(path, value)

        with patch("reconcile_review.write", side_effect=stop_before_request):
            self.assertEqual(self.call()["reconciliation"], "pending")
        self.assertTrue(crashed)
        record = (self.folder / "reconciliation.json").read_bytes()
        self.assertFalse((self.folder / "request.json").exists())
        self.assertEqual(self.call()["reconciliation"], "sealed")
        self.assertEqual((self.folder / "reconciliation.json").read_bytes(), record)

    def test_existing_different_request_is_not_repaired(self):
        different = {**self.request, "pr": 99}
        write(self.folder / "request.json", different)
        self.assertEqual(self.call()["reconciliation"], "pending")
        self.assertEqual(read(self.folder / "request.json"), different)
        self.assertFalse((self.folder / "reconciliation.json").exists())

    def test_recovery_commit_interruption_reuses_original_receipt(self):
        original_write = reconcile_review.write
        crashed = False

        def stop_before_terminal(path, value):
            nonlocal crashed
            if Path(path).name == "status.json" and value.get("reconciled") and not crashed:
                crashed = True
                raise OSError("Injected interruption before terminal commit")
            return original_write(path, value)

        with patch("reconcile_review.write", side_effect=stop_before_terminal):
            self.assertEqual(self.call()["reconciliation"], "pending")
        original_record = (self.folder / "reconciliation.json").read_bytes()
        self.assertEqual(self.call()["reconciliation"], "sealed")
        self.assertEqual((self.folder / "reconciliation.json").read_bytes(), original_record)

    def test_interrupted_atomic_control_writes_do_not_poison_sealed_manifest(self):
        for name in ("status.json.tmp", "evidence.json.tmp", "reconciliation.json.tmp"):
            (self.folder / name).write_text('{"partial":', encoding="utf-8")
        self.assertEqual(self.call()["reconciliation"], "sealed")
        manifest = read(self.folder / "evidence.json")["files"]
        self.assertEqual(verify_files(self.folder, manifest), [])
        self.assertNotIn("status.json.tmp", manifest)
        self.assertNotIn("evidence.json.tmp", manifest)

    def test_own_cleanup_block_is_archived_after_proof_without_rewriting_terminal(self):
        self.status.update(stage="error", verdict="INSUFFICIENT", finished=1)
        write(self.folder / "status.json", self.status)
        marker = dict(run_id=self.run, error="Original cleanup did not confirm exit")
        write(self.root / "cleanup-blocked.json", marker)
        before = {p.name: p.read_bytes() for p in self.folder.iterdir()}
        self.assertEqual(self.call()["reconciliation"], "cleanup-reconciled")
        self.assertFalse((self.root / "cleanup-blocked.json").exists())
        archive = self.root / "cleanup-resolutions"
        self.assertEqual(len(list(archive.glob("*.json"))), 2)
        self.assertEqual({p.name: p.read_bytes() for p in self.folder.iterdir()}, before)
        self.assertEqual(self.call()["reconciliation"], "already-terminal")

    def test_other_runs_cleanup_block_is_never_changed(self):
        marker = dict(run_id="issue-99-bbbbbbbbbbbb-r1", error="Other task")
        write(self.root / "cleanup-blocked.json", marker)
        self.assertEqual(self.call()["reconciliation"], "pending")
        self.assertEqual(read(self.root / "cleanup-blocked.json"), marker)
        self.assertFalse((self.root / "cleanup-resolutions").exists())

    @unittest.skipUnless(sys.platform.startswith("linux"), "Real inherited flock requires Linux")
    def test_parent_dies_after_model_popen_before_pid_write_but_child_keeps_lock(self):
        # This is an offline Python child, never an AI CLI or network operation.
        script = r'''
import fcntl,json,os,pathlib,subprocess,sys,time
root,folder=map(pathlib.Path,sys.argv[1:])
lock=(root/'worker.lock').open('r+')
fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
status=json.loads((folder/'status.json').read_text())
status.update(pid=os.getpid(),pid_start_ticks=pathlib.Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),worker_uid=os.getuid())
(folder/'status.json').write_text(json.dumps(status))
code="import pathlib,sys,time; p=pathlib.Path(sys.argv[1]); [(time.sleep(.01)) for _ in range(1000) if not p.exists()]"
with (folder/'stream.jsonl').open('a') as stream:
 child=subprocess.Popen([sys.executable,'-c',code,str(root/'release')],pass_fds=(lock.fileno(),),start_new_session=True,stdout=stream,stderr=stream)
 (root/'child-pid').write_text(str(child.pid))
os._exit(0)
'''
        parent = subprocess.Popen([sys.executable, "-c", script, str(self.root), str(self.folder)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            parent.communicate(timeout=5)
            self.assertEqual(parent.returncode, 0)
            self.assertNotIn("model_pid", read(self.folder / "status.json"))
            self.assertEqual(reconcile_review.reconcile(self.config, self.run)["reconciliation"], "pending")
            (self.root / "release").touch()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                result = reconcile_review.reconcile(self.config, self.run)
                if result["reconciliation"] == "sealed":
                    break
                time.sleep(.02)
            self.assertEqual(result["reconciliation"], "sealed", result)
            self.assertEqual(result["verdict"], "INSUFFICIENT")
        finally:
            (self.root / "release").touch()
            parent.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
