import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch, Mock
from pathlib import Path

from remote_dispatch import prepare_incoming, launch
from delivery import write


class DispatchTests(unittest.TestCase):
    def test_partial_upload_can_resume_but_launch_uncertainty_never_relaunches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = dict(remote_root=str(root))
            run = "issue-1-aaaaaaaaaaaa-r1"
            payload = b'{"repo":"test/project"}'
            manifest = {"request.json": hashlib.sha256(payload).hexdigest(), "local-evidence.json": hashlib.sha256(payload).hexdigest()}
            first = prepare_incoming(config, run, manifest)
            self.assertEqual(first["missing"], ["request.json", "local-evidence.json"])
            incoming = root / "incoming" / run
            (incoming / "request.json").write_bytes(payload)
            (incoming / "local-evidence.json").write_bytes(payload)
            self.assertEqual(prepare_incoming(config, run, manifest)["missing"], [])
            write(incoming / "launch-intent.json", {"run_id": run})
            result = launch(config, run)
            self.assertEqual(result["stage"], "launch-uncertain")
            self.assertFalse((incoming / "launch.json").exists())
            with self.assertRaises(RuntimeError):
                prepare_incoming(config, run, {**manifest, "request.json": "b" * 64})

    def test_proven_process_start_failure_allows_same_run_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = dict(remote_root=str(root))
            run = "issue-1-aaaaaaaaaaaa-r1"
            payload = b'{}'
            manifest = {name:hashlib.sha256(payload).hexdigest() for name in ("request.json","local-evidence.json")}
            prepare_incoming(config,run,manifest)
            incoming = root / "incoming" / run
            for name in manifest:
                (incoming / name).write_bytes(payload)
            with patch("remote_dispatch.subprocess.Popen",side_effect=FileNotFoundError("python3 missing")):
                with self.assertRaises(FileNotFoundError):
                    launch(config,run)
            with patch("remote_dispatch.subprocess.Popen",return_value=Mock(pid=1234)):
                self.assertEqual(launch(config,run)["stage"],"launched")


if __name__ == "__main__":
    unittest.main()
