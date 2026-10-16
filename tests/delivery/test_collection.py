"""Collect original bytes through the SSH/SCP boundary without launching work."""
import base64
import contextlib
import copy
import hashlib
import io
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from delivery import collect, run_id, write
from review_gate import digest


class CollectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="career-ops-collection-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = dict(repo="test/project", ssh_host="test-host", remote_root=self.root.as_posix().removeprefix(self.root.drive),
                           review_skill="matt-code-review", actual_models={"opus": "claude-opus-5-5"})
        self.request = dict(repo="test/project", issue=1, pr=2, round=1,
                            base_sha="a" * 40, head_sha="b" * 40, target_base_sha="a" * 40,
                            target_branch="main", expected_model="claude-opus-5-5",
                            review_skill="matt-code-review", criteria=["Collect original evidence"],
                            checks=[dict(name="check", host="linux", argv=["true"], timeout=10)])
        self.run = run_id(self.request)
        self.remote = self.root / "runs" / self.run
        self.remote.mkdir(parents=True)
        self.state = dict(run_id=self.run, request_digest=digest(self.request), stage="completed", finished=1)
        self.observed = {**self.state, "worker_alive": False, "model_alive": False}
        write(self.remote / "request.json", self.request)
        write(self.remote / "status.json", self.state)
        (self.remote / "stream.jsonl").write_bytes("原始审查输出\n".encode())
        (self.remote / "stderr.log").write_bytes(b"")
        (self.remote / "binary.log").write_bytes(bytes(range(256)))
        files = {p.name: self.sha(p) for p in self.remote.iterdir() if p.name != "status.json"}
        write(self.remote / "evidence.json", dict(request_digest=digest(self.request), files=files))
        self.manifest = {p.name: self.sha(p) for p in self.remote.iterdir()}
        self.transfers = []

    @staticmethod
    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def call(self, target, *, manifest=None, after=None, transport=None, real_snapshot=False):
        responses = [self.observed, dict(files=self.manifest if manifest is None else manifest),
                     self.observed if after is None else after]

        def ssh(command, **kwargs):
            self.assertEqual(command[0], "ssh")
            if real_snapshot and len(responses) == 2:
                encoded = re.search(r"b64decode\('([^']+)'\)", command[-1]).group(1)
                code = base64.b64decode(encoded).decode()
                process = subprocess.Popen([sys.executable, "-c", code], text=True,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                stdout, stderr = process.communicate(timeout=10)
                if process.returncode:
                    raise subprocess.CalledProcessError(process.returncode, command, stdout, stderr)
                responses.pop(0)
                return stdout
            return json.dumps(responses.pop(0))

        def scp(command, **kwargs):
            self.assertEqual(command[0], "scp")
            self.assertNotIn("-r", command)
            self.assertNotIn("-T", command)
            source, destination = command[-2:]
            self.assertFalse(source.endswith("/."), "Windows legacy scp rejects the dot filename")
            self.assertNotIn("*", source)
            name = source.rsplit("/", 1)[1]
            self.transfers.append(name)
            if transport:
                transport(name)
            Path(destination).write_bytes((self.remote / name).read_bytes())
            return subprocess.CompletedProcess(command, 0)

        with patch("delivery.subprocess.check_output", side_effect=ssh), \
                patch("delivery.subprocess.run", side_effect=scp), contextlib.redirect_stdout(io.StringIO()):
            return collect(self.config, self.run, target)

    def test_original_bytes_and_control_files_are_collected_with_explicit_filenames(self):
        target = self.root / "receipt"
        self.call(target)
        self.assertEqual({name: self.sha(target / name) for name in self.manifest}, self.manifest)
        collection = json.loads((target / "collection.json").read_text())
        self.assertEqual(collection["transport_files"], self.manifest)
        self.assertEqual(collection["request_digest"], digest(self.request))
        self.assertEqual(set(self.transfers), set(self.manifest))

    def test_running_or_uncertain_round_is_not_collected(self):
        for state in (dict(stage="model-review", worker_alive=True, model_alive=True),
                      dict(stage="completed", worker_alive=False, model_alive=True),
                      dict(stage="launch-uncertain", worker_alive=False, model_alive=False),
                      dict(stage="completed"),
                      dict(stage="completed", worker_alive=0, model_alive=False)):
            with self.subTest(state=state):
                self.observed = {**self.state, **state}
                target = self.root / "not-created"
                with self.assertRaisesRegex(RuntimeError, "terminal"):
                    self.call(target)
                self.assertFalse(target.exists())
        self.assertEqual(self.transfers, [])


    def test_partial_transfer_preserved_and_same_run_recovers_only_into_new_directory(self):
        partial = self.root / "partial"

        def disconnect(name):
            if len(self.transfers) == 2:
                raise subprocess.CalledProcessError(1, "scp", stderr="connection lost")

        with self.assertRaises(subprocess.CalledProcessError):
            self.call(partial, transport=disconnect)
        before = {p.name: p.read_bytes() for p in partial.iterdir()}
        self.assertTrue(before)
        self.assertFalse((partial / "collection.json").exists())
        with self.assertRaises(FileExistsError):
            self.call(partial)
        self.call(self.root / "recovered")
        self.assertEqual({p.name: p.read_bytes() for p in partial.iterdir()}, before)
        self.assertTrue((self.root / "recovered/collection.json").is_file())

    def test_unsafe_names_aliases_and_missing_controls_rejected_before_transfer(self):
        for name in ("../escape", "/absolute", "nested/file", "nested\\file", "C:ads", "NUL.log",
                     "COM1", "Lpt9.txt", "trailing.", "collection.json", "Status.json"):
            with self.subTest(name=name):
                manifest = {**self.manifest, name: "a" * 64}
                with self.assertRaisesRegex(RuntimeError, "Unsafe"):
                    self.call(self.root / "unsafe", manifest=manifest)
                self.assertFalse((self.root / "unsafe").exists())
        for name in ("request.json", "status.json", "evidence.json"):
            with self.subTest(missing=name):
                manifest = {key: value for key, value in self.manifest.items() if key != name}
                with self.assertRaisesRegex(RuntimeError, "incomplete"):
                    self.call(self.root / "missing", manifest=manifest)
        self.assertEqual(self.transfers, [])

    def test_damaged_log_or_control_file_never_publishes_collection(self):
        for name in ("stream.jsonl", "status.json", "evidence.json"):
            original = (self.remote / name).read_bytes()
            target = self.root / ("damaged-" + name)

            def tamper(current):
                if current == name:
                    (self.remote / name).write_bytes(original + b" ")

            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, "incomplete or changed"):
                self.call(target, transport=tamper)
            self.assertFalse((target / "collection.json").exists())
            (self.remote / name).write_bytes(original)

    def test_terminal_drift_or_live_child_after_transfer_never_publishes_collection(self):
        for index, change in enumerate((dict(finished=2), dict(stage="model-review"),
                                        dict(model_alive=True), dict(worker_alive=None))):
            target = self.root / f"changed-{index}"
            with self.subTest(change=change), self.assertRaisesRegex(RuntimeError, "changed during collection"):
                self.call(target, after={**self.observed, **change})
            self.assertFalse((target / "collection.json").exists())

    def test_request_digest_and_original_run_are_rechecked(self):
        self.observed["request_digest"] = "c" * 64
        target = self.root / "wrong-request"
        with self.assertRaisesRegex(RuntimeError, "request differs"):
            self.call(target)
        self.assertFalse((target / "collection.json").exists())
        self.observed["run_id"] = "issue-9-aaaaaaaaaaaa-r1"
        transfers = list(self.transfers)
        with self.assertRaisesRegex(RuntimeError, "round identity"):
            self.call(self.root / "wrong-run")
        self.assertEqual(self.transfers, transfers)

    def test_remote_snapshot_reads_actual_files_and_rejects_non_regular_artifacts(self):
        self.call(self.root / "actual-snapshot", real_snapshot=True)
        (self.remote / "unexpected-directory").mkdir()
        transfers = list(self.transfers)
        with self.assertRaises(subprocess.CalledProcessError):
            self.call(self.root / "non-regular", real_snapshot=True)
        self.assertEqual(self.transfers, transfers)
        self.assertFalse((self.root / "non-regular").exists())

    @unittest.skipUnless(sys.platform.startswith("linux"), "Remote symlink source is a Linux boundary")
    def test_remote_snapshot_rejects_symlink_even_when_target_is_a_regular_file(self):
        (self.remote / "linked.log").symlink_to(self.remote / "stream.jsonl")
        with self.assertRaises(subprocess.CalledProcessError):
            self.call(self.root / "symlink", real_snapshot=True)
        self.assertEqual(self.transfers, [])


if __name__ == "__main__":
    unittest.main()
