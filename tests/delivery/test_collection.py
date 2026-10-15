"""A live process or a changed terminal receipt must not become merge evidence."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from delivery import collect


class CollectionTests(unittest.TestCase):
    def test_running_or_uncertain_round_is_not_collected(self):
        config = dict(repo="test/project", ssh_host="test-host", remote_root="/tmp/test")
        for status in (dict(stage="model-review",worker_alive=True,model_alive=True),
                       dict(stage="completed",worker_alive=False,model_alive=True),
                       dict(stage="launch-uncertain",worker_alive=False,model_alive=False)):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "new-receipt"
                with patch("delivery.subprocess.check_output",return_value=json.dumps(status)), contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(RuntimeError,"terminal"):
                        collect(config,"issue-1-aaaaaaaaaaaa-r1",target)
                self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
