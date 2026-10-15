"""Durable serial delivery decisions; the owning Codex thread performs each action.

No model dispatcher is hidden here. A pending operation is reconciled by its
original identity; time passing never grants a replacement writer permission.
"""
import argparse
import contextlib
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from delivery import HERE, read, write, output, run_id, files_index
from review_gate import (IDENTITY, digest, gate, validate_request, verify_files, review_model,
                         codex_gate, review_contract, review_context_digest)


@contextlib.contextmanager
def state_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_suffix(".lock").open("a+b") as handle:
        if os.name == "nt":
            import msvcrt
            handle.seek(0)
            if not handle.read(1):
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def validate_queue(queue):
    if not queue.get("authorization") or not queue.get("coordinator_thread"):
        raise ValueError("Explicit authorization and coordinator thread required")
    issues = queue.get("issues", [])
    ids = [i["issue"] for i in issues]
    if not ids or len(ids) != len(set(ids)) or any(type(i) is not int or i < 1 for i in ids):
        raise ValueError("Unique positive Issue numbers required")
    visited = set()
    for item in issues:
        if not re.fullmatch(r"[a-z]+\([a-z0-9-]+\): .+", item.get("title", "")):
            raise ValueError("Issue title must name a clear type(scope): outcome")
        dependencies = item.get("dependencies", [])
        if not isinstance(dependencies, list) or not set(dependencies).issubset(visited):
            raise ValueError("Queue must be topologically ordered with known dependencies")
        visited.add(item["issue"])


def next_action(state):
    active = state.get("active")
    if active:
        if active.get("retry_at", 0) > time.time():
            return dict(action="wait", issue=active["issue"], retry_at=active["retry_at"], reason=active["retry_reason"])
        if active.get("pending"):
            return dict(action="reconcile", issue=active["issue"], operation=active["pending"])
        return dict(action=active["stage"], issue=active["issue"], owner=active["owner"])
    completed = {i for i, receipt in state["completed"].items() if receipt.get("closed")}
    for item in state["queue"]:
        if str(item["issue"]) not in completed and all(str(d) in completed for d in item["dependencies"]):
            return dict(action="claim", issue=item["issue"], title=item["title"])
    return dict(action="complete" if len(completed) == len(state["queue"]) else "blocked")


def claim(state, args):
    previous = state["operations"].get(args.operation)
    if previous:
        if previous != dict(issue=args.issue, owner=args.owner, action="claim"):
            raise ValueError("Operation identity already belongs to another action")
        return previous
    action = next_action(state)
    if action.get("action") != "claim" or action.get("issue") != args.issue:
        raise ValueError("Another writer is active or dependencies have not completed")
    receipt = dict(issue=args.issue, owner=args.owner, action="claim")
    state["active"] = {**receipt, "stage": "implement", "sessions": {}, "reviews": [], "round": 0}
    state["operations"][args.operation] = receipt
    return receipt


def active_issue(state):
    if not state.get("active"):
        raise ValueError("No claimed Issue")
    return state["active"]


def record_retry(state, args):
    active = active_issue(state)
    value = datetime.fromisoformat(args.at)
    if value.tzinfo is None or value.timestamp() <= time.time():
        raise ValueError("Retry requires a future timestamp with timezone")
    evidence = args.evidence.resolve()
    active.update(retry_at=value.timestamp(), retry_reason=args.reason,
                  retry_evidence=dict(path=str(evidence), files=files_index(evidence.parent, [evidence.name])))
    return next_action(state)


def record_intent(state, args):
    active = active_issue(state)
    if args.operation in state["operations"]:
        previous = state["operations"][args.operation]
        if previous.get("issue") != active["issue"] or previous.get("request_digest") != digest(active.get("review_request")):
            raise ValueError("Operation identity already belongs to another candidate")
        return previous
    if active.get("pending"):
        raise ValueError("Reconcile the existing pending operation before dispatching")
    request = active.get("review_request")
    if args.kind != "review" or not request or active["stage"] != "review":
        raise ValueError("Review intent requires a pinned candidate ready for review")
    intent = dict(kind="review", operation=args.operation, issue=active["issue"], run_id=run_id(request),
                  request_digest=digest(request), created=time.time())
    active["pending"] = intent
    state["operations"][args.operation] = intent
    return intent


def record_candidate(state, args):
    active = active_issue(state)
    if active.get("pending") or active["owner"] != args.owner:
        raise ValueError("Pending work must be reconciled by the original implementation owner")
    request = read(args.request)
    validate_request(request, read(args.config))
    if request["issue"] != active["issue"] or request["round"] <= active["round"]:
        raise ValueError("Candidate must belong to the active Issue with a fresh round")
    previous = active.get("candidate")
    if previous and request["pr"] != previous["pr"]:
        raise ValueError("Repairs must update the original PR")
    checkout = args.checkout.resolve()
    if output(["git", "rev-parse", "HEAD"], checkout) != request["head_sha"] or output(["git", "status", "--porcelain"], checkout):
        raise ValueError("Candidate is dirty or HEAD differs from request")
    branch = output(["git", "branch", "--show-current"], checkout)
    if not re.fullmatch(rf"[a-z]+/issue-{active['issue']}-[a-z0-9]+(?:-[a-z0-9]+)*", branch):
        raise ValueError("Branch must use type/issue-N-clear-description")
    if output(["git", "merge-base", request["target_base_sha"], request["head_sha"]], checkout) != request["target_base_sha"]:
        raise ValueError("Review an integration candidate containing the target base")
    if review_model(request) != "opus":
        if not previous or review_contract(request) != review_contract(previous):
            raise ValueError("Fable escalation must address the exact existing Opus candidate")
        if not args.escalation_reason:
            raise ValueError("Fable needs a substantive discussion reason; quota is a retry")
        active["fable_required"] = True
        active["escalation_reason"] = args.escalation_reason
    else:
        active["candidate"] = request
        active.pop("codex_acceptance", None)
        active.pop("opus_receipt", None)
    active.update(review_request=request, checkout=str(checkout), branch=branch,
                  round=request["round"], stage="review")
    active.pop("retry_at", None)
    return dict(issue=active["issue"], head_sha=request["head_sha"], run_id=run_id(request), action="review")


def consensus_stage(active):
    if active.get("pending"):
        return
    request = active["candidate"]
    opus = active.get("opus_receipt", {})
    fable = active.get("fable_receipt", {})
    if opus.get("request_digest") != digest(request):
        active["stage"] = "review-retry"
    elif active.get("fable_required") and (not fable.get("context_digest")
            or fable["context_digest"] != opus.get("context_digest")):
        active["stage"] = "fable-review"
    elif not active.get("codex_acceptance"):
        active["stage"] = "codex-acceptance"
    else:
        active["stage"] = "merge"


def record_acceptance(state, args):
    active = active_issue(state)
    if active["owner"] != args.owner or not active.get("candidate"):
        raise ValueError("Only the original implementation owner accepts the pinned candidate")
    acceptance = read(args.receipt)
    problems = codex_gate(active["candidate"], acceptance)
    if problems:
        raise ValueError(str(problems))
    destination = args.state.parent / "acceptance" / (run_id(active["candidate"]) + ".json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and read(destination) != acceptance:
        raise ValueError("Acceptance is immutable; use a new candidate round")
    if not destination.exists():
        write(destination, acceptance)
    active["codex_acceptance"] = dict(path=str(destination.resolve()), digest=digest(acceptance))
    consensus_stage(active)
    return next_action(state)


def record_review(state, args):
    active = active_issue(state)
    pending = active.get("pending", {})
    folder = args.folder.resolve()
    request = read(folder / "request.json")
    if pending.get("kind") != "review" or pending.get("request_digest") != digest(request):
        raise ValueError("Receipt must resolve the exact pending review operation")
    validate_request(request, read(args.config))
    evidence, status = read(folder / "evidence.json"), read(folder / "status.json")
    collection = read(folder / "collection.json")
    observed = collection.get("status", {})
    if (status.get("run_id") != run_id(request) or observed.get("run_id") != run_id(request)
            or status.get("stage") not in ("completed", "error") or observed.get("worker_alive") is not False
            or observed.get("model_alive") is not False or evidence.get("request_digest") != digest(request)
            or collection.get("request_digest") != digest(request)
            or any(observed.get(key) != status.get(key) for key in ("request_digest", "finished", "stage"))):
        raise ValueError("Review is not a collected, stopped terminal round")
    problems = verify_files(folder, evidence.get("files"))
    if problems:
        raise ValueError(str(problems))
    role = "opus" if review_model(request) == "opus" else "fable"
    session = evidence.get("session_id")
    if session and session == evidence.get("init_session_id"):
        previous = active["sessions"].get(role)
        if previous and previous != session:
            raise ValueError("Review repair must resume this model's original session")
        active["sessions"][role] = session
    report = read(folder / "report.json") if (folder / "report.json").exists() else None
    problems = gate(request, report, evidence)
    passed = status.get("verdict") == "PASS" and not problems
    receipt = dict(path=str(folder), request_digest=digest(request), identity={key: request[key] for key in IDENTITY},
                   role=role, verdict="PASS" if passed else "CHANGES_REQUIRED" if isinstance(report, dict)
                   and report.get("verdict") == "CHANGES_REQUIRED" else "INSUFFICIENT", problems=problems,
                   evidence_digest=digest(evidence), status_digest=digest(status), session_id=session,
                   context_digest=review_context_digest(request, evidence) if passed else None)
    active["reviews"].append(receipt)
    active.pop("pending")
    active.pop("retry_at", None)
    if passed:
        active[role + "_receipt"] = receipt
        consensus_stage(active)
    else:
        active.pop(role + "_receipt", None)
        active["stage"] = "implement" if receipt["verdict"] == "CHANGES_REQUIRED" else "review-retry"
    return dict(**next_action(state), review=receipt)


def merge_candidate(state, args):
    from finish_delivery import finish
    if str(args.issue) in state["completed"]:
        return state["completed"][str(args.issue)]
    active = active_issue(state)
    if active["issue"] != args.issue or active["stage"] != "merge":
        raise ValueError("Both Codex and Opus must accept this exact candidate before merge")
    if active.get("pending", {}).get("kind") not in (None, "merge"):
        raise ValueError("A different pending operation must be reconciled first")
    request = active["candidate"]
    checkout = Path(active["checkout"])
    if output(["git", "rev-parse", "HEAD"], checkout) != request["head_sha"] or output(["git", "status", "--porcelain"], checkout):
        raise ValueError("Implementation checkout changed since candidate acceptance")
    acceptance = active["codex_acceptance"]
    if digest(read(acceptance["path"])) != acceptance["digest"]:
        raise ValueError("Stored Codex acceptance changed")
    contexts = set()
    for role in ("opus", "fable") if active.get("fable_required") else ("opus",):
        receipt = active[role + "_receipt"]
        folder = Path(receipt["path"])
        reviewed_request, evidence = read(folder / "request.json"), read(folder / "evidence.json")
        if (review_contract(reviewed_request) != review_contract(request)
                or digest(evidence) != receipt["evidence_digest"]
                or digest(read(folder / "status.json")) != receipt["status_digest"]
                or gate(reviewed_request, read(folder / "report.json"), evidence)
                or verify_files(folder, evidence.get("files"))):
            raise ValueError(f"Stored {role} review changed or no longer passes")
        context = review_context_digest(reviewed_request, evidence)
        if context != receipt.get("context_digest"):
            raise ValueError(f"Stored {role} review context changed")
        contexts.add(context)
    if len(contexts) != 1:
        raise ValueError("Opus and Fable must accept the same current review context and specifications")
    if not active.get("pending"):
        active["pending"] = dict(kind="merge", issue=args.issue, request_digest=digest(request), created=time.time())
        state["revision"] += 1
        state["events"].append(dict(revision=state["revision"], time=time.time(), command="merge-intent", result=active["pending"]))
        write(args.state, state)
    receipt = finish(read(args.config), Path(active["opus_receipt"]["path"]), Path(active["checkout"]),
                     Path(acceptance["path"]), reconcile_operation=args.reconcile_operation)
    if not receipt.get("closed"):
        raise RuntimeError("Finish did not prove merge and Issue closure")
    state["completed"][str(args.issue)] = receipt
    state["active"] = None
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=HERE / "project.json")
    parser.add_argument("--state", type=Path, default=HERE.parents[1] / "local/delivery/state.json")
    parser.add_argument("--revision", type=int)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init").add_argument("queue", type=Path)
    commands.add_parser("next")
    commands.add_parser("show")
    command = commands.add_parser("claim")
    command.add_argument("--issue", type=int, required=True)
    command.add_argument("--owner", required=True)
    command.add_argument("--operation", required=True)
    command = commands.add_parser("merge")
    command.add_argument("--issue", type=int, required=True)
    command.add_argument("--reconcile-operation", choices=("merge", "close"))
    command = commands.add_parser("intent")
    command.add_argument("--kind", choices=["review"], required=True)
    command.add_argument("--operation", required=True)
    command = commands.add_parser("retry")
    command.add_argument("--at", required=True)
    command.add_argument("--reason", required=True)
    command.add_argument("--evidence", type=Path, required=True)
    command = commands.add_parser("candidate")
    command.add_argument("request", type=Path)
    command.add_argument("--checkout", type=Path, required=True)
    command.add_argument("--owner", required=True)
    command.add_argument("--escalation-reason")
    commands.add_parser("review").add_argument("folder", type=Path)
    command = commands.add_parser("accept")
    command.add_argument("receipt", type=Path)
    command.add_argument("--owner", required=True)
    args = parser.parse_args()
    config = read(args.config)
    with state_lock(args.state):
        if args.command == "init":
            if args.state.exists():
                raise ValueError("State already exists; resume it instead of replacing it")
            queue = read(args.queue)
            validate_queue(queue)
            state = dict(schema_version=1, revision=0, repo=config["repo"], authorization=queue["authorization"],
                         coordinator_thread=queue["coordinator_thread"], queue=queue["issues"], active=None,
                         completed={}, operations={}, events=[])
            result = next_action(state)
        else:
            state = read(args.state)
            if state["repo"] != config["repo"]:
                raise ValueError("State belongs to another repository")
            if args.revision is not None and args.revision != state["revision"]:
                raise ValueError("State revision changed; read before deciding again")
            if args.command in ("next", "show"):
                print(json.dumps(next_action(state) if args.command == "next" else state))
                return
            result = {"claim": claim, "intent": record_intent, "retry": record_retry,
                      "candidate": record_candidate, "review": record_review,
                      "accept": record_acceptance, "merge": merge_candidate}[args.command](state, args)
        state["revision"] += 1
        state["events"].append(dict(revision=state["revision"], time=time.time(), command=args.command, result=result))
        write(args.state, state)
        print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, KeyError) as error:
        print(f"{type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(2)
