"""Idempotent upload and at-most-once launch on the review host."""
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path

from coordinator import state_lock
from delivery import read, write
from review_gate import verify_files


def incoming_path(config, run):
    if not re.fullmatch(r"issue-\d+-[a-f0-9]{12}-r\d+", run):
        raise ValueError("Invalid run ID")
    return Path(config["remote_root"]) / "incoming" / run


def prepare_incoming(config, run, manifest):
    incoming = incoming_path(config, run)
    if "request.json" not in manifest or "local-evidence.json" not in manifest:
        raise ValueError("Request and local evidence must be in upload manifest")
    if any(not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", name) or not re.fullmatch(r"[a-f0-9]{64}", sha) for name, sha in manifest.items()):
        raise ValueError("Plain filenames and SHA-256 digests required")
    incoming.mkdir(parents=True, exist_ok=True)
    with state_lock(incoming / "upload"):
        index = incoming / "upload-manifest.json"
        if index.exists() and read(index) != manifest:
            raise RuntimeError("Existing run belongs to a different payload")
        if not index.exists():
            write(index, manifest)
        missing = [name for name, sha in manifest.items()
                   if not (incoming / name).is_file() or hashlib.sha256((incoming / name).read_bytes()).hexdigest() != sha]
        launched = (incoming / "launch-intent.json").exists()
        if missing and launched:
            raise RuntimeError("Launched payload changed; never overwrite its evidence")
        return dict(run_id=run, missing=missing, launch_intent=launched)


def publish(config, run, name):
    incoming = incoming_path(config, run)
    with state_lock(incoming / "upload"):
        manifest = read(incoming / "upload-manifest.json")
        if name not in manifest or Path(name).name != name:
            raise ValueError("Unexpected uploaded file")
        staged = incoming / (name + ".upload")
        if (incoming / "launch-intent.json").exists():
            raise RuntimeError("Launch already attempted; preserve payload")
        if hashlib.sha256(staged.read_bytes()).hexdigest() != manifest[name]:
            raise RuntimeError("Upload incomplete or changed")
        staged.replace(incoming / name)


def launch(config, run):
    incoming = incoming_path(config, run)
    with state_lock(incoming / "upload"):
        status = Path(config["remote_root"]) / "runs" / run / "status.json"
        if status.exists():
            return read(status)
        if (incoming / "launch.json").exists():
            return read(incoming / "launch.json")
        intent_path = incoming / "launch-intent.json"
        previous = read(intent_path) if intent_path.exists() else {}
        if previous and previous.get("outcome") != "not_sent":
            return dict(run_id=run, stage="launch-uncertain", action="reconcile-original-run")
        problems = verify_files(incoming, read(incoming / "upload-manifest.json"))
        if problems:
            raise RuntimeError(f"Incomplete upload: {problems}")
        attempt = dict(run_id=run, time=time.time(), attempt=previous.get("attempt", 0) + 1, outcome="unknown")
        write(intent_path, attempt)
        root = Path(config["remote_root"])
        environment = os.environ.copy()
        environment["PATH"] = str(Path.home() / ".local/bin") + os.pathsep + environment.get("PATH", "")
        log_name = "launcher.log" if attempt["attempt"] == 1 else f"launcher-{attempt['attempt']}.log"
        try:
            with (incoming / log_name).open("x") as log:
                process = subprocess.Popen(["python3", str(root / "tools/review_worker.py"), "--incoming", str(incoming)],
                                           cwd=root, env=environment, stdin=subprocess.DEVNULL,
                                           stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        except OSError as error:
            # Popen did not create a child. Unlike a lost SSH ACK, this proves
            # the original run is safe to retry after repairing infrastructure.
            attempt.update(outcome="not_sent", error=f"{type(error).__name__}: {error}")
            write(intent_path, attempt)
            write(incoming / f"launch-failure-{attempt['attempt']}.json", attempt)
            raise
        receipt = dict(run_id=run, stage="launched", pid=process.pid)
        write(incoming / "launch.json", receipt)
        return receipt
