"""Seal a stopped original review as INSUFFICIENT without launching a model."""

import argparse
import contextlib
import hashlib
import json
import os
import re
import stat
import time
import uuid
from pathlib import Path

from delivery import HERE, read, run_id, write
from review_gate import digest, validate_request, verify_files


class Unverified(RuntimeError):
    """Evidence cannot establish that the original round is stopped."""


@contextlib.contextmanager
def original_worker_lock(path, expected):
    """Use the existing inode; creating a replacement lock proves nothing."""
    try:
        import fcntl
    except ImportError as error:
        raise Unverified("Linux worker-lock verification is unavailable") from error
    if path.is_symlink():
        raise Unverified("Worker lock is a symbolic link")
    with path.open("r+") as stream:
        details = os.fstat(stream.fileno())
        actual = dict(device=details.st_dev, inode=details.st_ino)
        if not stat.S_ISREG(details.st_mode) or actual != expected:
            raise Unverified("Original worker-lock identity changed")
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise Unverified("Original worker or inherited child still holds the lock") from error
        try:
            yield actual
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def proc_stat(path):
    fields = path.read_text().rsplit(")", 1)[1].split()
    return dict(state=fields[0], parent=int(fields[1]), group=int(fields[2]),
                session=int(fields[3]), start_ticks=fields[19])


def process_evidence(status, folder, incoming, proc_root=Path("/proc"), uid=None):
    """Read process metadata and this round's open-log identities, never cmdlines."""
    uid = os.getuid() if uid is None else uid
    boot = (proc_root / "sys/kernel/random/boot_id").read_text().strip()
    previous_boot = status.get("boot_id")
    if (str(uuid.UUID(boot)) != boot or str(uuid.UUID(previous_boot)) != previous_boot
            or uid != status.get("worker_uid")):
        raise Unverified("Original boot or worker-user identity is unverified")
    boot_changed = boot != previous_boot
    proof = dict(boot_id=boot, previous_boot_id=previous_boot, boot_changed=boot_changed,
                 worker_uid=uid, processes={}, related_processes=[], excluded_preexisting_processes=[])
    original_ids = set()
    for role, pid_key, start_key in (("worker", "pid", "pid_start_ticks"),
                                    ("model", "model_pid", "model_start_ticks")):
        pid, start = status.get(pid_key), status.get(start_key)
        if role == "model" and pid is None and start is None:
            proof["processes"][role] = dict(identity="not_recorded", start_outcome="unknown")
            continue
        if type(pid) is not int or pid <= 0 or not isinstance(start, str) or not start.isdigit():
            raise Unverified(f"Original {role} PID and birth identity are incomplete")
        if boot_changed:
            proof["processes"][role] = dict(pid=pid, start_ticks=start, state="previous_boot_ended")
            continue
        original_ids.add(pid)
        try:
            observed = proc_stat(proc_root / str(pid) / "stat")
        except FileNotFoundError:
            proof["processes"][role] = dict(pid=pid, start_ticks=start, state="absent")
            continue
        if observed["start_ticks"] != start:
            raise Unverified(f"Original {role} PID was reused; do not infer its process tree")
        if observed["state"] not in ("Z", "X"):
            raise Unverified(f"Original {role} is still active")
        proof["processes"][role] = dict(pid=pid, start_ticks=start, state=observed["state"])

    proof["inherited_lock"] = "exclusive_lock_acquired"
    proof["model_completion"] = "not_asserted"
    if boot_changed:
        # A verified new boot ends every original process, even when the model
        # PID was never saved. Current-boot descriptors cannot belong to them.
        proof["descriptor_scan"] = "not_required_previous_boot_ended"
        return proof

    # A model can inherit the lock and log descriptors before its PID is saved.
    # Check only descriptor targets matching this run, without reading contents
    # or inspecting other tasks' arguments/environment.
    log_ids = set()
    paths = [folder / "stream.jsonl", *folder.glob("*.log"), *incoming.glob("launcher*.log")]
    for path in paths:
        if path.is_file():
            details = path.stat()
            log_ids.add((details.st_dev, details.st_ino))
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if entry.stat().st_uid != uid:
                continue
            observed = proc_stat(entry / "stat")
            if observed["state"] in ("Z", "X"):
                continue
            if any(observed[key] in original_ids for key in ("parent", "group", "session")):
                raise Unverified("A process remains in the original worker/model tree")
            if not observed["start_ticks"].isdigit():
                raise Unverified("Observed process birth identity is incomplete")
            # On the same boot, an unrelated process born before the worker
            # cannot be its descendant. Equal ticks remain ambiguous.
            if int(observed["start_ticks"]) < int(status["pid_start_ticks"]):
                proof["excluded_preexisting_processes"].append(
                    dict(pid=int(entry.name), start_ticks=observed["start_ticks"]))
                continue
            for descriptor in (entry / "fd").iterdir():
                try:
                    details = descriptor.stat()
                except FileNotFoundError:
                    continue
                if (details.st_dev, details.st_ino) in log_ids:
                    raise Unverified("A process still holds this round's model or launcher log")
        except FileNotFoundError:
            continue  # Process exited while its metadata was being sampled.
    return proof


def file_manifest(folder, excluded=()):
    result = {}
    for path in folder.iterdir():
        # Atomic control-write leftovers are not committed evidence; the writes
        # below consume these exact temporary names before the round is sealed.
        if path.name in (*excluded, "request.json.tmp", "status.json.tmp", "evidence.json.tmp", "reconciliation.json.tmp"):
            continue
        if path.is_symlink() or not path.is_file():
            raise Unverified("Unexpected non-file review artifact")
        result[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def original_identity(config, run, incoming, folder):
    manifest = read(incoming / "upload-manifest.json")
    if not isinstance(manifest, dict) or not {"request.json", "local-evidence.json"} <= set(manifest):
        raise Unverified("Original upload manifest is incomplete")
    if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name)
           or not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value)
           for name, value in manifest.items()):
        raise Unverified("Original upload manifest is malformed")
    if verify_files(incoming, manifest):
        raise Unverified("Original uploaded evidence changed")
    request = read(incoming / "request.json")
    validate_request(request, config)
    request_path = folder / "request.json"
    request_missing = not request_path.exists()
    if (run_id(request) != run or request_path.is_symlink()
            or not request_missing and read(request_path) != request):
        raise Unverified("Run does not match its original request")
    if read(incoming / "local-evidence.json").get("request_digest") != digest(request):
        raise Unverified("Original local evidence belongs to another request")
    status = read(folder / "status.json")
    if status.get("run_id") != run or status.get("request_digest") != digest(request):
        raise Unverified("Worker status belongs to another request")
    return request, status, manifest, request_missing


def resolve_cleanup(root, run, marker, status, proof):
    """Archive this run's block only after persisting its verified resolution."""
    if marker is None:
        return
    marker_path = root / "cleanup-blocked.json"
    if marker.get("run_id") != run or read(marker_path) != marker:
        raise Unverified("Cleanup block belongs to another run or changed")
    archive = root / "cleanup-resolutions"
    archive.mkdir(exist_ok=True)
    key = run + "-" + digest(marker)[:16]
    resolution_path, archived_marker = archive / (key + ".json"), archive / (key + ".marker.json")
    if resolution_path.exists():
        resolution = read(resolution_path)
        if resolution.get("original_marker") != marker or resolution.get("run_id") != run:
            raise Unverified("Existing cleanup resolution identity changed")
    else:
        write(resolution_path, dict(run_id=run, original_marker=marker, status_digest=digest(status),
                                   process_evidence=proof, resolved_at=time.time()))
    if archived_marker.exists():
        raise Unverified("Cleanup archive already exists while a block remains; preserve both")
    marker_path.rename(archived_marker)


def reconcile(config, run):
    """Return pending unless the existing run can be sealed under its own lock."""
    if not re.fullmatch(r"issue-\d+-[a-f0-9]{12}-r\d+", run):
        raise ValueError("Invalid run ID")
    root = Path(config["remote_root"])
    incoming, folder = root / "incoming" / run, root / "runs" / run
    pending = dict(run_id=run, reconciliation="pending", stage="unverified")
    try:
        if incoming.is_symlink() or folder.is_symlink():
            raise Unverified("Original review directories must not be symbolic links")
        if not (folder / "status.json").exists():
            raise Unverified("Original worker status is absent; launch history remains unknown")
        request, status, manifest, request_missing = original_identity(config, run, incoming, folder)
        pending["stage"] = status.get("stage", "unverified")
        marker_path = root / "cleanup-blocked.json"
        marker = read(marker_path) if marker_path.exists() else None
        if marker is not None and marker.get("run_id") != run:
            raise Unverified("Another run owns the unresolved cleanup block")
        if status.get("stage") in ("completed", "error") and request_missing:
            raise Unverified("Terminal review request is missing; preserve the sealed round")
        if status.get("stage") in ("completed", "error") and marker is None:
            return {**status, "reconciliation": "already-terminal"}
        if (not isinstance(status.get("boot_id"), str) or not status["boot_id"]
                or type(status.get("worker_uid")) is not int
                or not isinstance(status.get("worker_lock"), dict)
                or any(type(status["worker_lock"].get(key)) is not int for key in ("device", "inode"))):
            raise Unverified("Original boot, user or lock identity was not recorded")
        with original_worker_lock(root / "worker.lock", status["worker_lock"]):
            # The initial read can race a live worker finishing before we lock.
            request, status, manifest, request_missing = original_identity(config, run, incoming, folder)
            proof = process_evidence(status, folder, incoming)
            if status.get("stage") in ("completed", "error"):
                if request_missing:
                    raise Unverified("Terminal review request is missing; preserve the sealed round")
                resolve_cleanup(root, run, marker, status, proof)
                return {**status, "reconciliation": "cleanup-reconciled" if marker else "already-terminal"}
            record_path = folder / "reconciliation.json"
            if record_path.exists():
                record = read(record_path)
                if (record.get("run_id") != run or record.get("request_digest") != digest(request)
                        or record.get("original_status") != status
                        or record.get("upload_manifest") != manifest
                        or not isinstance(record.get("preserved_files"), dict)
                        or not record["preserved_files"] and record.get("original_request_missing") is not True
                        or record["preserved_files"] and verify_files(folder, record["preserved_files"])):
                    raise Unverified("Existing recovery record belongs to different or changed evidence")
            else:
                evidence_path = folder / "evidence.json"
                evidence = read(evidence_path) if evidence_path.exists() else {}
                if evidence.get("request_digest", digest(request)) != digest(request):
                    raise Unverified("Original review evidence belongs to another request")
                if evidence.get("files") and verify_files(folder, evidence["files"]):
                    raise Unverified("Original review artifact manifest changed")
                record = dict(run_id=run, request_digest=digest(request), upload_manifest=manifest,
                    original_status=status, original_evidence=evidence, process_evidence=proof,
                    original_request_missing=request_missing,
                    preserved_files=file_manifest(folder, ("status.json", "evidence.json")),
                    observed_at=time.time(), verdict="INSUFFICIENT",
                    reason="Original worker stopped without a terminal review outcome; startup history is not inferred")
                write(record_path, record)
            if request_missing:
                if not record.get("original_request_missing"):
                    raise Unverified("Request disappeared after recovery began; preserve the evidence")
                # This copy is justified by the pinned upload and status digest,
                # only after exclusive-lock and stopped-process verification.
                write(folder / "request.json", request)
            evidence = {**record["original_evidence"], "request_digest": digest(request),
                        "reconciliation": "reconciliation.json"}
            if status.get("session_id"):
                if evidence.get("session_id", status["session_id"]) != status["session_id"]:
                    raise Unverified("Original session identities disagree")
                evidence["session_id"] = status["session_id"]
            evidence["files"] = file_manifest(folder, ("status.json", "evidence.json"))
            write(folder / "evidence.json", evidence)
            sealed = {**status, "stage": "error", "verdict": "INSUFFICIENT",
                      "finished": record["observed_at"], "reconciled": True,
                      "reconciliation_digest": digest(record), "error": record["reason"]}
            write(folder / "status.json", sealed)
            resolve_cleanup(root, run, marker, sealed, proof)
            return {**sealed, "reconciliation": "sealed"}
    except (Unverified, OSError, ValueError, KeyError, TypeError, IndexError) as error:
        return {**pending, "reason": str(error)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=HERE / "project.json")
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    result = reconcile(read(args.config), args.run)
    print(json.dumps(result, ensure_ascii=False))
    return 2 if result["reconciliation"] == "pending" else 0


if __name__ == "__main__":
    raise SystemExit(main())
