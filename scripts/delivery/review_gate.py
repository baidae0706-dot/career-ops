"""Candidate-bound acceptance checks. This is a coordinator gate, not a sandbox."""

import hashlib
import json
import re
from pathlib import Path

IDENTITY = ("repo", "issue", "pr", "base_sha", "head_sha", "target_base_sha", "target_branch")


def repository_matches(remote, repo):
    value = remote.rstrip("/").removesuffix(".git")
    return value in (f"https://github.com/{repo}", f"git@github.com:{repo}", f"ssh://git@github.com/{repo}")


def review_model(request):
    model = request.get("review_model", "opus")
    if model not in ("opus", "claude-fable-5-1"):
        raise ValueError("Unsupported review model; explicit supported model required")
    return model


def models_match(models, expected):
    if not isinstance(models, list) or not models:
        return False
    return all(isinstance(model, str) and model == expected for model in models)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def spec_digest(value):
    return digest({k: value.get(k) for k in ("title", "body", "comments")})


def review_contract(request):
    """Model and attempt selection do not change the work being reviewed."""
    return {key: value for key, value in request.items()
            if key not in ("round", "review_model", "expected_model")}


def review_context_digest(request, evidence):
    specifications = {"issue_digest": evidence.get("issue_digest"),
                      "parent_digest": evidence.get("parent_digest") if request.get("parent_issue") else None}
    required = ("issue_digest", "parent_digest") if request.get("parent_issue") else ("issue_digest",)
    if any(not isinstance(specifications[key], str) or not re.fullmatch(r"[a-f0-9]{64}", specifications[key]) for key in required):
        raise ValueError("Actual Issue and parent specification digests are required for acceptance")
    return digest(dict(request=review_contract(request), **specifications))


def validate_title(title):
    if (not isinstance(title, str) or title != title.strip()
            or not re.fullmatch(r"[a-z]+\([a-z0-9-]+\): \S[^\r\n]*", title)):
        raise ValueError("Issue and PR titles must name a clear type(scope): outcome")


def validate_branch(branch, issue):
    if not isinstance(branch, str) or not re.fullmatch(rf"[a-z]+/issue-{issue}-[a-z0-9]+(?:-[a-z0-9]+)*", branch):
        raise ValueError("Branch must use type/issue-N-clear-description for this Issue")


def validate_request(request, config):
    model = review_model(request)
    if request.get("expected_model") != config.get("actual_models", {}).get(model) or not request.get("expected_model"):
        raise ValueError("Actual model must be pinned by project configuration")
    if request.get("review_skill") != config.get("review_skill") or not request.get("review_skill"):
        raise ValueError("Explicit review skill must match project configuration")
    if request.get("repo") != config["repo"]:
        raise ValueError("Wrong repository")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", config["repo"]):
        raise ValueError("Repository must be owner/name")
    if "remote_root" in config and not re.fullmatch(r"/[A-Za-z0-9_./-]+", config["remote_root"]):
        raise ValueError("Remote root must be an absolute path with safe characters")
    if "ssh_host" in config and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", config["ssh_host"]):
        raise ValueError("SSH host must be a configured host alias")
    for key in ("issue", "pr", "round"):
        if type(request.get(key)) is not int or request[key] < 1:
            raise ValueError(f"Invalid {key}")
    if request.get("parent_issue") is not None and (
        type(request["parent_issue"]) is not int or request["parent_issue"] < 1
    ):
        raise ValueError("Invalid parent issue")
    for key in ("base_sha", "head_sha", "target_base_sha"):
        if not re.fullmatch(r"[a-f0-9]{40}", request.get(key, "")):
            raise ValueError(f"Invalid immutable {key}")
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._/-]*", request.get("target_branch", "")):
        raise ValueError("Invalid target branch")
    criteria = request.get("criteria")
    if not isinstance(criteria, list) or not criteria or any(
        not isinstance(c, str) or not c.strip() for c in criteria
    ):
        raise ValueError("Explicit complete acceptance criteria required")
    checks = request.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("At least one explicit check required")
    names = set()
    for check in checks:
        name = check.get("name", "")
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", name) or name in names:
            raise ValueError("Check names must be unique safe filenames")
        names.add(name)
        if check.get("host") not in ("windows", "linux"):
            raise ValueError("Check execution host required")
        argv = check.get("argv")
        if not isinstance(argv, list) or not argv or any(not isinstance(a, str) for a in argv):
            raise ValueError("Check argv must be an argument array")
        if type(check.get("timeout")) is not int or not 1 <= check["timeout"] <= 7200:
            raise ValueError("Bounded check timeout required")


def verify_files(folder, index):
    problems = []
    root = Path(folder).resolve()
    if not isinstance(index, dict) or not index:
        return ["Evidence file manifest missing"]
    for relative, expected in index.items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            problems.append(f"Missing or escaped evidence: {relative}")
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            problems.append(f"Changed evidence: {relative}")
    return problems


def codex_gate(request, acceptance):
    if not isinstance(acceptance, dict):
        return ["Codex acceptance missing"]
    problems = []
    if any(acceptance.get(key) != request.get(key) for key in IDENTITY) or acceptance.get("request_digest") != digest(request):
        problems.append("Codex acceptance belongs to another candidate or request")
    if acceptance.get("verdict") != "PASS":
        problems.append("Codex has not accepted the candidate")
    findings = acceptance.get("findings")
    if not isinstance(findings, list) or any(not isinstance(item, dict) or item.get("blocking", True) for item in findings):
        problems.append("Codex findings are unresolved")
    items = acceptance.get("acceptance")
    if (not isinstance(items, list) or any(not isinstance(item, dict) for item in items)
            or len(items) != len(request["criteria"]) or any(type(item.get("index")) is not int for item in items)
            or {item.get("index") for item in items} != set(range(1, len(request["criteria"]) + 1))):
        problems.append("Codex acceptance coverage incomplete")
    elif any(item.get("status") != "PASS" or not isinstance(item.get("evidence"), str) or not item["evidence"].strip() for item in items):
        problems.append("Codex acceptance evidence incomplete")
    return problems


def gate(request, report, evidence):
    problems = []
    expected_model = request.get("expected_model")
    if not isinstance(report, dict):
        return ["Structured review report missing"]
    for key in IDENTITY:
        if report.get(key) != request.get(key):
            problems.append(f"Report {key} differs from request")
    if evidence.get("request_digest") != digest(request):
        problems.append("Request changed since execution")
    if evidence.get("head_before") != request["head_sha"] or evidence.get("head_after") != request["head_sha"]:
        problems.append("Candidate changed")
    if evidence.get("dirty_before") or evidence.get("dirty_after"):
        problems.append("Candidate is dirty")
    checks = evidence.get("checks", {})
    expected = {c["name"]: c for c in request["checks"]}
    if set(checks) != set(expected):
        problems.append("Required checks missing or unexpected")
    for name, check in expected.items():
        result = checks.get(name, {})
        if (result.get("exit_code") != 0 or result.get("host") != check["host"]
                or result.get("argv") != check["argv"] or result.get("head_sha") != request["head_sha"]
                or result.get("log") not in evidence.get("files", {})):
            problems.append(f"Invalid check evidence: {name}")
    if evidence.get("process_exit") != 0 or evidence.get("model_error", True) or evidence.get("model_timeout"):
        problems.append("Model process failed")
    if not evidence.get("session_id") or evidence.get("init_session_id") != evidence.get("session_id"):
        problems.append("Actual review session is not verified")
    skill = evidence.get("skill", {})
    if skill.get("name") != request.get("review_skill") or skill.get("loaded") is not True:
        problems.append("Review skill did not actually load")
    skill_order = (skill.get("mechanism") == "Skill" and bool(skill.get("tool_use_id"))
                   and skill.get("session_id") == evidence.get("session_id")
                   and skill.get("args") == request["base_sha"]
                   and isinstance(skill.get("call_message_id"), str) and bool(skill["call_message_id"])
                   and type(skill.get("call_event")) is int and type(skill.get("result_event")) is int
                   and 0 <= skill["call_event"] < skill["result_event"])
    if not skill_order or "stream.jsonl" not in evidence.get("files", {}):
        problems.append("Successful parent Skill invocation is not bound to this run and base")
    models = evidence.get("parent_models", [])
    if not models_match(models, expected_model):
        problems.append(f"Main model is not verified {expected_model}")
    if not {"standards-reviewer", "spec-reviewer"}.issubset(evidence.get("agents_invoked", [])):
        problems.append("Both independent review axes must run")
    submodels = evidence.get("subagent_models", {})
    if len(submodels) < 2 or any(not models_match(ms, expected_model) for ms in submodels.values()):
        problems.append(f"Two actual {expected_model} subagent transcripts required")
    axes = evidence.get("axes", {})
    agent_ids, call_ids, call_messages = set(), set(), set()
    for axis in ("standards", "spec"):
        value = axes.get(axis, {})
        if (not value.get("completed") or value.get("status") != "PASS" or not value.get("summary")
                or not models_match(value.get("models"), expected_model)
                or value.get("report") not in evidence.get("files", {})
                or value.get("raw_report") not in evidence.get("files", {})
                or value.get("transcript") not in evidence.get("files", {})
                or not isinstance(value.get("findings"), list)
                or any(not isinstance(f, dict) or f.get("blocking", True) for f in value.get("findings", []))):
            problems.append(f"Completed passing {axis} child report not verified")
        if (not skill_order or value.get("session_id") != evidence.get("session_id")
                or value.get("run_in_background") is not False
                or type(value.get("call_event")) is not int or value["call_event"] <= skill["result_event"]
                or not isinstance(value.get("call_message_id"), str) or not value.get("call_message_id")
                or value.get("call_message_id") == skill.get("call_message_id")):
            problems.append(f"{axis} must start in the parent after successful Skill loading")
        call_messages.add(value.get("call_message_id"))
        agent_ids.add(value.get("agent_id"))
        call_ids.add(value.get("tool_use_id"))
    if None in call_messages or len(call_messages) != 1:
        problems.append("Both foreground axes must share one assistant tool-call batch")
    if None in agent_ids or len(agent_ids) != 2 or None in call_ids or len(call_ids) != 2:
        problems.append("Review axes are not bound to distinct actual children")
    for axis in ("standards", "spec"):
        value = report.get(axis, {})
        if not isinstance(value, dict) or value.get("status") != "PASS" or not value.get("summary"):
            problems.append(f"{axis} did not pass")
    items = report.get("acceptance", [])
    if not isinstance(items, list) or any(not isinstance(i, dict) for i in items):
        return problems + ["Invalid acceptance list"]
    if len(items) != len(request["criteria"]) or {i.get("index") for i in items} != set(range(1, len(request["criteria"]) + 1)):
        problems.append("Incomplete acceptance coverage")
    if any(i.get("status") != "PASS" or not i.get("evidence") for i in items):
        problems.append("Acceptance evidence not passing")
    findings = report.get("findings")
    if not isinstance(findings, list) or any(not isinstance(f, dict) or f.get("blocking", True) for f in findings):
        problems.append("Unresolved or malformed findings")
    if report.get("verdict") != "PASS":
        problems.append("Reviewer did not return PASS")
    return problems
