"""Reconcile one accepted candidate through squash merge, receipt and Issue closure.

The caller supplies the reviewed receipt and Codex's independent agreement.
Mutable finish records live beside that immutable receipt, never inside it.
"""

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import subprocess
import uuid
from pathlib import Path

from delivery import HERE, output, premerge, read, terminate_tree, write
from review_gate import codex_gate, digest, gate, spec_digest, validate_request, verify_files


def file_digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def comment_digest(body):
    return hashlib.sha256(body.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def github(config, *args):
    command = ["gh", *args]
    if args[0] != "api":
        command.extend(["--repo", config["repo"]])
    return output(command)


def github_json(config, *args):
    return json.loads(github(config, *args))


def safe_log(text):
    text = re.sub(r"(?im)^(?:authorization|proxy-authorization|cookie|set-cookie):.*$", "[redacted header]", text)
    return re.sub(r"\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b", "[redacted token]", text)


def failed_request_outcome(stdout, stderr, method, endpoint):
    """Only single-request evidence can prove a failed mutation did not commit."""
    statuses = re.findall(r"(?m)^HTTP/\S+ (\d{3})(?:\s|$)", stdout)
    # 408, 5xx, redirects and unknown responses remain ambiguous. No timed retry.
    if (stdout.startswith("HTTP/") and len(statuses) == 1
            and int(statuses[0]) in (400, 401, 403, 404, 405, 409, 410, 415, 422, 429)):
        return "rejected", f"http_{statuses[0]}"
    prefix = re.escape(f'{method.title()} "https://api.github.com/{endpoint}": dial tcp')
    dns = r": lookup api\.github\.com(?: on [^\n]+)?: (?:no such host|temporary failure in name resolution)"
    refused = r" [^\n]+: connect: connection refused"
    if not statuses and re.fullmatch(prefix + "(?:" + dns + "|" + refused + ")\\s*", stderr):
        return "not_sent", "connection_not_established"
    return "unknown", "unconfirmed_response"


def send_mutation(config, state, state_path, destination, operation, method, endpoint, payload):
    """Persist one attempt and issue one REST mutation, with no implicit retries.

    REST's sha parameter is GitHub's exact-head merge condition:
    https://docs.github.com/en/rest/pulls/pulls#merge-a-pull-request
    """
    if state.get("pending") not in (None, operation):
        raise RuntimeError("A different operation has an unresolved outcome")
    attempt = dict(id=str(uuid.uuid4()), operation=operation, method=method, endpoint=endpoint,
                   payload_sha256=digest(payload), outcome="unknown")
    attempt_dir = destination / "attempts" / attempt["id"]
    attempt_dir.mkdir(parents=True, exist_ok=False)
    request_path = attempt_dir / "request.json"
    write(request_path, payload)
    state.setdefault("attempts", []).append(attempt)
    state["pending"] = operation
    write(state_path, state)
    command = ["gh", "api", endpoint, "--hostname", "github.com", "--method", method,
               "--header", "Accept: application/vnd.github+json",
               "--header", "X-GitHub-Api-Version: 2026-03-10", "--include", "--input", str(request_path)]
    env = {**os.environ, "GH_DEBUG": "", "GH_PROMPT_DISABLED": "1", "NO_COLOR": "1"}

    def record(outcome, reason, stdout="", stderr="", returncode=None):
        for name, value in (("stdout", stdout), ("stderr", stderr)):
            (attempt_dir / f"{name}.log").write_text(safe_log(value), encoding="utf-8", newline="\n")
        attempt.update(outcome=outcome, reason=reason, returncode=returncode,
                       stdout_sha256=file_digest(attempt_dir / "stdout.log"),
                       stderr_sha256=file_digest(attempt_dir / "stderr.log"))
        write(attempt_dir / "result.json", attempt)
        if outcome in ("not_sent", "rejected"):
            state["pending"] = None
        write(state_path, state)

    try:
        options = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
                   else {"start_new_session": True})
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding="utf-8", env=env, **options)
    except OSError as error:
        # Popen failed before the GitHub program was started; unlike communicate
        # errors this is affirmative evidence that no request was sent.
        record("not_sent", "process_not_started", stderr=str(error))
        raise
    try:
        stdout, stderr = process.communicate(timeout=60)
    except BaseException:
        try:
            terminate_tree(process)
            stdout, stderr = process.communicate(timeout=10)
        except BaseException as error:
            write(destination / "cleanup-blocked.json", dict(attempt_id=attempt["id"],
                operation=operation, error=safe_log(str(error))))
            record("unknown", "cleanup_failed", stderr=safe_log(str(error)), returncode=process.returncode)
            raise RuntimeError("Mutation process cleanup unresolved; preserve the blocking marker") from error
        record("unknown", "process_interrupted", stdout, stderr, process.returncode)
        raise
    if process.returncode:
        outcome, reason = failed_request_outcome(stdout, stderr, method, endpoint)
        record(outcome, reason, stdout, stderr, process.returncode)
        raise subprocess.CalledProcessError(process.returncode, command, output=safe_log(stdout), stderr=safe_log(stderr))
    record("acknowledged", "readback_required", stdout, stderr, process.returncode)


def recover_recorded_attempt(state, state_path, destination):
    """Replay a verified terminal result if a crash interrupted the state write."""
    if not state.get("pending") or not state.get("attempts"):
        return
    attempt = state["attempts"][-1]
    attempt_id = str(uuid.UUID(attempt["id"]))
    if attempt_id != attempt["id"] or attempt["operation"] != state["pending"]:
        raise RuntimeError("Finish attempt identity is inconsistent")
    directory = destination / "attempts" / attempt_id
    result_path = directory / "result.json"
    if not result_path.exists():
        return
    result = read(result_path)
    keys = ("id", "operation", "method", "endpoint", "payload_sha256")
    if (any(result.get(key) != attempt.get(key) for key in keys)
            or digest(read(directory / "request.json")) != attempt["payload_sha256"]
            or any(file_digest(directory / f"{name}.log") != result.get(f"{name}_sha256")
                   for name in ("stdout", "stderr"))):
        raise RuntimeError("Persisted mutation result does not match its attempt")
    if result.get("outcome") not in ("not_sent", "rejected", "unknown", "acknowledged"):
        raise RuntimeError("Persisted mutation result has an invalid outcome")
    state["attempts"][-1] = result
    if result["outcome"] in ("not_sent", "rejected"):
        state["pending"] = None
    write(state_path, state)


def all_issue_comments(config, issue):
    # --jq emits one complete JSON object per line across every page, including
    # on the VPS's gh 2.45; --slurp requires a newer client.
    raw = github(config, "api", f"repos/{config['repo']}/issues/{issue}/comments?per_page=100",
                 "--paginate", "--jq", ".[]")
    comments = [json.loads(line) for line in raw.splitlines() if line.strip()]
    if any(not isinstance(comment, dict) or not isinstance(comment.get("body"), str) for comment in comments):
        raise RuntimeError("Complete comment readback is malformed")
    return comments


def verified_acceptance(config, folder, codex_path):
    request, report, evidence, status = [read(folder / name) for name in
        ("request.json", "report.json", "evidence.json", "status.json")]
    validate_request(request, config)
    if request.get("review_model", "opus") != "opus":
        raise RuntimeError("A Fable escalation cannot replace the required Opus acceptance")
    problems = gate(request, report, evidence) + verify_files(folder, evidence.get("files"))
    if status.get("verdict") != "PASS" or problems:
        raise RuntimeError(f"Acceptance gate not satisfied: {problems}")
    problems = codex_gate(request, read(codex_path))
    if problems:
        raise RuntimeError(f"Codex agreement not satisfied: {problems}")
    return request, report, evidence


def verify_specifications(config, request, evidence, planned_comment=None):
    own_comment = None
    current_issue = None
    for key, number in (("issue", request["issue"]), ("parent", request.get("parent_issue"))):
        if number is None:
            continue
        snapshot = github_json(config, "issue", "view", str(number), "--json", "title,body,comments,state")
        if key == "issue":
            current_issue = snapshot
            if planned_comment:
                matches = [comment for comment in all_issue_comments(config, number)
                           if comment["body"].startswith(planned_comment["marker"])]
                if len(matches) > 1 or any(comment_digest(c["body"]) != planned_comment["body_sha256"] for c in matches):
                    raise RuntimeError("Published acceptance comment changed or was duplicated")
                own_comment = matches[0] if matches else None
            comments = []
            for comment in snapshot.get("comments", []):
                body = comment.get("body", "")
                if planned_comment and body.startswith(planned_comment["marker"]):
                    if not own_comment or comment_digest(body) != planned_comment["body_sha256"]:
                        raise RuntimeError("Acceptance comment readbacks disagree")
                else:
                    comments.append(comment)
            snapshot = {**snapshot, "comments": comments}
        if spec_digest(snapshot) != evidence[f"{key}_digest"]:
            raise RuntimeError(f"{key} specification changed since review")
    return current_issue, own_comment


def read_pr(config, request):
    pr = github_json(config, "pr", "view", str(request["pr"]), "--json",
                     "headRefOid,baseRefName,state,mergeCommit")
    if (pr["headRefOid"], pr["baseRefName"]) != (request["head_sha"], request["target_branch"]):
        raise RuntimeError("PR identity changed since review")
    return pr


def acceptance_comment(request, report, evidence, merge_sha, tree, codex_sha):
    marker = f"<!-- delivery-acceptance:{request['repo']}:{request['issue']}:{digest(request)} -->"
    lines = [marker, "## Codex 与 VPS Opus 验收通过", "",
        f"审查提交：`{request['head_sha']}`；比较基线：`{request['base_sha']}`。",
        f"PR #{request['pr']} 已 Squash 合并为 `{merge_sha}`。",
        f"集成父提交：`{request['target_base_sha']}`；合并树与审查树 `{tree}` 相同。", "",
        f"Standards：{report['standards']['summary']}", f"Spec：{report['spec']['summary']}", "",
        "逐项验收："]
    lines.extend(f"- {item['index']}. {item['status']} — {item['evidence']}" for item in report["acceptance"])
    lines.extend(["", f"实际审查模型：`{', '.join(evidence['parent_models'])}`；两路实际子审查均已校验。",
        f"请求摘要：`{digest(request)}`；Codex 同意回执 SHA-256：`{codex_sha}`。",
        "限制：" + ("；".join(report.get("limitations", [])) or "无新增限制。")])
    body = "\n".join(lines) + "\n"
    return dict(marker=marker, body=body, body_sha256=comment_digest(body))


def finish(config, folder, checkout, codex_acceptance=None, reconcile_operation=None):
    """Finish or resume this exact receipt; never repeats a confirmed external write."""
    from coordinator import state_lock

    if reconcile_operation not in (None, "merge", "close"):
        raise ValueError("Only exact-identity merge or close may be reconciled for retry")
    folder, checkout = Path(folder).resolve(), Path(checkout).resolve()
    destination = folder.with_name(folder.name + ".finish")
    destination.mkdir(exist_ok=True)
    with state_lock(destination / "state.json"):
        if (destination / "cleanup-blocked.json").exists():
            raise RuntimeError("Mutation process cleanup unresolved; inspect cleanup-blocked.json")
        return finish_locked(config, folder, checkout, Path(codex_acceptance).resolve()
            if codex_acceptance else folder / "codex-acceptance.json", destination, reconcile_operation)


def finish_locked(config, folder, checkout, codex_path, destination, reconcile_operation):
    if config.get("merge_method") != "squash":
        raise RuntimeError("Only the configured squash merge is supported")
    request, report, evidence = verified_acceptance(config, folder, codex_path)
    identity = dict(request_digest=digest(request), evidence_digest=digest(evidence),
                    report_sha256=file_digest(folder / "report.json"), codex_sha256=file_digest(codex_path))
    state_path = destination / "state.json"
    state = read(state_path) if state_path.exists() else {"identity": identity}
    if state.get("identity") != identity:
        raise RuntimeError("Finish records belong to a different acceptance receipt")
    recover_recorded_attempt(state, state_path, destination)
    write(state_path, state)
    verify_specifications(config, request, evidence, state.get("comment"))
    pr = read_pr(config, request)
    tree = output(["git", "rev-parse", request["head_sha"] + "^{tree}"], checkout)
    output(["git", "merge-base", "--is-ancestor", request["target_base_sha"], request["head_sha"]], checkout)
    remote_head = github_json(config, "api", f"repos/{config['repo']}/commits/{request['head_sha']}")
    if remote_head["commit"]["tree"]["sha"] != tree:
        raise RuntimeError("Local candidate tree differs from the remote reviewed head")
    if pr["state"] == "OPEN":
        if state.get("merge_sha") or state.get("comment") or state.get("pending") in ("comment", "close"):
            raise RuntimeError("PR readback reverted to an earlier merge phase; retain the current intent")
        if state.get("pending") == "merge" and reconcile_operation != "merge":
            raise RuntimeError("Merge outcome is unknown; reconcile before another send")
        settings = github_json(config, "api", f"repos/{config['repo']}")
        if not settings.get("allow_squash_merge"):
            raise RuntimeError("Repository does not permit squash merge")
        target = github_json(config, "api", f"repos/{config['repo']}/git/ref/heads/{request['target_branch']}")
        if target["object"]["sha"] != request["target_base_sha"]:
            raise RuntimeError("Live target branch changed since review")
        with contextlib.redirect_stdout(io.StringIO()):
            premerge(config, folder)
        if state.get("pending") == "merge":
            state.setdefault("reconciliations", []).append(dict(operation="merge", reason="exact_head_open_and_gates_rechecked"))
        send_mutation(config, state, state_path, destination, "merge", "PUT",
                      f"repos/{config['repo']}/pulls/{request['pr']}/merge",
                      dict(sha=request["head_sha"], merge_method="squash"))
        pr = read_pr(config, request)
    if pr["state"] != "MERGED" or not pr.get("mergeCommit"):
        raise RuntimeError("Merge is not confirmed; preserve the pending operation")
    merge_sha = pr["mergeCommit"]["oid"]
    commit = github_json(config, "api", f"repos/{config['repo']}/commits/{merge_sha}")
    if [parent["sha"] for parent in commit["parents"]] != [request["target_base_sha"]]:
        raise RuntimeError("Merged parent differs from reviewed integration; do not close Issue")
    if commit["commit"]["tree"]["sha"] != tree:
        raise RuntimeError("Merged tree differs from reviewed candidate; do not close Issue")
    state.update(merge_sha=merge_sha, tree=tree)
    if state.get("pending") == "merge":
        state["pending"] = None
    proposed = acceptance_comment(request, report, evidence, merge_sha, tree, identity["codex_sha256"])
    if state.get("comment", proposed) != proposed:
        raise RuntimeError("Stored acceptance comment differs from this verified merge")
    state["comment"] = proposed
    write(state_path, state)
    issue, own_comment = verify_specifications(config, request, evidence, proposed)
    if not own_comment:
        if state.get("pending") == "comment" or state.get("comment_confirmed"):
            raise RuntimeError("Acceptance comment outcome is unknown; reconcile before another send")
        body_path = destination / "acceptance.md"
        body_path.write_text(proposed["body"], encoding="utf-8", newline="\n")
        send_mutation(config, state, state_path, destination, "comment", "POST",
                      f"repos/{config['repo']}/issues/{request['issue']}/comments", dict(body=proposed["body"]))
        issue, own_comment = verify_specifications(config, request, evidence, proposed)
        if not own_comment:
            raise RuntimeError("Acceptance comment not confirmed")
    state.update(comment_id=own_comment.get("id"), comment_confirmed=True)
    if state.get("pending") == "comment":
        state["pending"] = None
    write(state_path, state)
    if issue["state"] != "CLOSED":
        if state.get("pending") == "close" and reconcile_operation != "close":
            raise RuntimeError("Issue closure outcome is unknown; reconcile before another send")
        if state.get("pending") == "close":
            state.setdefault("reconciliations", []).append(dict(operation="close", reason="verified_merge_and_issue_open"))
        send_mutation(config, state, state_path, destination, "close", "PATCH",
                      f"repos/{config['repo']}/issues/{request['issue']}", dict(state="closed", state_reason="completed"))
        issue, own_comment = verify_specifications(config, request, evidence, proposed)
    if issue["state"] != "CLOSED" or not own_comment:
        raise RuntimeError("Issue closure not confirmed; preserve the pending operation")
    receipt = dict(closed=True, repo=config["repo"], issue=request["issue"], pr=request["pr"],
        head=request["head_sha"], merge_sha=merge_sha, tree=tree, parent=request["target_base_sha"],
        merge_method="squash", comment_sha256=proposed["body_sha256"], **identity)
    write(destination / "closure.json", receipt)
    state.update(pending=None, closed=True)
    write(state_path, state)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=HERE / "project.json")
    parser.add_argument("receipt", type=Path)
    parser.add_argument("--checkout", required=True, type=Path)
    parser.add_argument("--codex-acceptance", type=Path)
    parser.add_argument("--reconcile-operation", choices=("merge", "close"))
    args = parser.parse_args()
    print(json.dumps(finish(read(args.config), args.receipt, args.checkout, args.codex_acceptance,
                            args.reconcile_operation), ensure_ascii=False))


if __name__ == "__main__":
    main()
