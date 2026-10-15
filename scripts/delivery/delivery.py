"""Prepare Windows evidence, dispatch to VPS, retrieve and recheck a candidate."""

import argparse
import base64
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

from review_gate import digest, gate, spec_digest, validate_request, verify_files

HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def output(argv, cwd=None):
    return subprocess.check_output(argv, cwd=cwd, text=True, encoding="utf-8").strip()


def run_id(request):
    return f"issue-{request['issue']}-{request['head_sha'][:12]}-r{request['round']}"


class CleanupError(RuntimeError):
    """A task's process tree could not be confirmed stopped."""


def terminate_tree(process):
    if os.name == "nt":
        try:
            result = subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                    capture_output=True, text=True, timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise CleanupError(f"Cannot stop process tree {process.pid}: {error}") from error
        if result.returncode != 0:
            raise CleanupError(f"Cannot stop process tree {process.pid}: {result.stderr.strip()}")
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except OSError as error:
            raise CleanupError(f"Cannot stop process group {process.pid}: {error}") from error
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired as error:
        raise CleanupError(f"Process {process.pid} did not exit after tree termination") from error


def execute_checks(request, host, checkout, folder, lock_fd=None):
    results = {}
    for check in request["checks"]:
        if check["host"] != host:
            continue
        log = f"{host}-{check['name']}.log"
        with (folder / log).open("w", encoding="utf-8") as stream:
            try:
                options = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt"
                           else {"start_new_session": True, "pass_fds": (() if lock_fd is None else (lock_fd,))})
                process = subprocess.Popen(check["argv"], cwd=checkout, stdout=stream,
                                           stderr=subprocess.STDOUT, **options)
                try:
                    code = process.wait(timeout=check["timeout"])
                except BaseException:
                    terminate_tree(process)
                    raise
            except subprocess.TimeoutExpired:
                stream.write("\nCHECK TIMED OUT\n")
                code = 124
            except OSError as error:
                stream.write(f"\nCHECK COULD NOT START: {error}\n")
                code = 127
        results[check["name"]] = dict(exit_code=code, host=host, argv=check["argv"],
                                    head_sha=request["head_sha"], log=log)
    return results


def files_index(folder, names):
    return {name: hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in names}


def gh(config, *args):
    return json.loads(output(["gh", *args, "--repo", config["repo"]]))


def live_candidate(config, request):
    pr = gh(config, "pr", "view", str(request["pr"]), "--json",
            "headRefOid,baseRefName,state,isDraft,mergeable,statusCheckRollup")
    # gh 2.45 does not expose baseRefOid in pr view. Obtain the same pinned
    # identity from the REST pull endpoint and reject cross-read drift.
    if "baseRefOid" not in pr:
        identity = json.loads(output(["gh", "api", f"repos/{config['repo']}/pulls/{request['pr']}"]))
        if (identity["head"]["sha"], identity["base"]["ref"]) != (pr["headRefOid"], pr["baseRefName"]):
            raise RuntimeError("Live PR identity changed between metadata reads")
        pr["baseRefOid"] = identity["base"]["sha"]
    if (pr["headRefOid"], pr["baseRefOid"], pr["baseRefName"]) != (
        request["head_sha"], request["target_base_sha"], request["target_branch"]
    ):
        raise RuntimeError("Live PR candidate differs from pinned request")
    return pr


def prepare(config, source, checkout, folder):
    request = read(source)
    validate_request(request, config)
    blocked = checkout / "local/delivery/cleanup-blocked.json"
    if blocked.exists():
        raise RuntimeError(f"Prior process cleanup unresolved; inspect {blocked} before another run")
    if any(c["host"] == "windows" for c in request["checks"]) and os.name != "nt":
        raise RuntimeError("Windows checks require Windows")
    if output(["git", "rev-parse", "HEAD"], checkout) != request["head_sha"]:
        raise RuntimeError("Local candidate SHA mismatch")
    if output(["git", "status", "--porcelain"], checkout):
        raise RuntimeError("Local candidate is dirty; preserve it")
    folder.mkdir(parents=True, exist_ok=False)
    write(folder / "request.json", request)
    try:
        checks = execute_checks(request, "windows", checkout, folder)
    except CleanupError as error:
        blocked.parent.mkdir(parents=True, exist_ok=True)
        write(blocked, dict(error=str(error), run=run_id(request), receipt=str(folder)))
        raise
    if (output(["git", "rev-parse", "HEAD"], checkout) != request["head_sha"]
            or output(["git", "status", "--porcelain"], checkout)):
        raise RuntimeError("Local checks changed candidate; do not dispatch")
    write(folder / "local-evidence.json", dict(request_digest=digest(request), checks=checks,
          files=files_index(folder, [c["log"] for c in checks.values()])))
    print(json.dumps(dict(run_id=run_id(request), directory=str(folder), checks=checks)))


def remote(config, code):
    encoded = base64.b64encode(code.encode()).decode()
    return output(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15", config["ssh_host"],
                   f"python3 -c \"import base64;exec(base64.b64decode('{encoded}'))\""])


def dispatch(config, folder):
    request = read(folder / "request.json")
    validate_request(request, config)
    local = read(folder / "local-evidence.json")
    if local["request_digest"] != digest(request) or (local["checks"] and verify_files(folder, local["files"])):
        raise RuntimeError("Local evidence changed")
    if any(c["exit_code"] != 0 for c in local["checks"].values()):
        raise RuntimeError("Local check failure; repair before dispatch")
    if any(not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", name) for name in local["files"]):
        raise RuntimeError("Evidence must use plain filenames")
    live_candidate(config, request)
    run = run_id(request)
    incoming = config["remote_root"] + "/incoming/" + run
    manifest = files_index(folder, ["request.json", "local-evidence.json", *local["files"]])
    prefix = f"import sys,json;sys.path.insert(0,{config['remote_root'] + '/tools'!r});import remote_dispatch as d\n"
    state = json.loads(remote(config, prefix + f"print(json.dumps(d.prepare_incoming({config!r},{run!r},{manifest!r})))"))
    for file in state["missing"]:
        subprocess.run(["scp", "-O", "-q", "-o", "ConnectTimeout=15", str(folder / file),
                        f"{config['ssh_host']}:{incoming}/{file}.upload"], check=True)
        remote(config, prefix + f"d.publish({config!r},{run!r},{file!r})")
    result = json.loads(remote(config, prefix + f"print(json.dumps(d.launch({config!r},{run!r})))"))
    print(json.dumps(result))
    return result


def status(config, run, emit=True):
    code = f'''import json,pathlib
root=pathlib.Path({config['remote_root']!r})
p=root/'runs'/{run!r}/'status.json'
s=json.loads(p.read_text()) if p.exists() else {{'stage':'not-started'}}
for prefix,pid_key,start_key in [('worker','pid','pid_start_ticks'),('model','model_pid','model_start_ticks')]:
 try:
  fields=pathlib.Path('/proc/'+str(s[pid_key])+'/stat').read_text().rsplit(')',1)[1].split()
  s[prefix+'_alive']=fields[19]==s[start_key] and fields[0]!='Z'
 except (KeyError,FileNotFoundError):
  s[prefix+'_alive']=False
if s.get('stage')=='not-started':
 incoming=root/'incoming'/{run!r}
 if (incoming/'launch.json').exists():
  s.update(json.loads((incoming/'launch.json').read_text()))
 elif (incoming/'launch-intent.json').exists():
  intent=json.loads((incoming/'launch-intent.json').read_text())
  s['stage']='launch-not-sent' if intent.get('outcome')=='not_sent' else 'launch-uncertain'
  s['action']='retry-original-run' if intent.get('outcome')=='not_sent' else 'reconcile-original-run'
 log=incoming/'launcher.log'
 s['launcher_tail']=log.read_text()[-1000:] if log.exists() else ''
print(json.dumps(s,ensure_ascii=False))
'''
    value = json.loads(remote(config, code))
    if emit:
        print(json.dumps(value))
    return value


def collect(config, run, folder):
    current = status(config, run, emit=False)
    if current.get("stage") not in ("completed", "error") or current.get("worker_alive") or current.get("model_alive"):
        raise RuntimeError("Only a terminal, stopped original round may be collected")
    folder.mkdir(parents=True, exist_ok=False)
    subprocess.run(["scp", "-O", "-q", "-o", "ConnectTimeout=15", "-r",
                    f"{config['ssh_host']}:{config['remote_root']}/runs/{run}/.", str(folder)], check=True)
    evidence = read(folder / "evidence.json")
    problems = verify_files(folder, evidence.get("files"))
    if problems:
        raise RuntimeError(f"Receipt is incomplete or changed: {problems}; preserve it and collect into a fresh directory")
    collected = read(folder / "status.json")
    if any(collected.get(key) != current.get(key) for key in ("run_id", "request_digest", "finished", "stage")):
        raise RuntimeError("Terminal status changed during collection")
    write(folder / "collection.json", dict(status=current, request_digest=evidence.get("request_digest")))
    print(json.dumps(dict(directory=str(folder), run_id=run)))


def premerge(config, folder):
    request, report, evidence, state = [read(folder / n) for n in
                                      ("request.json", "report.json", "evidence.json", "status.json")]
    validate_request(request, config)
    problems = gate(request, report, evidence) + verify_files(folder, evidence.get("files"))
    if state.get("verdict") != "PASS" or problems:
        raise RuntimeError(f"Acceptance not satisfied: {problems}")
    for key, number in (("issue", request["issue"]), ("parent", request.get("parent_issue"))):
        if number is None:
            continue
        live = gh(config, "issue", "view", str(number), "--json", "title,body,comments")
        if spec_digest(live) != evidence[f"{key}_digest"]:
            raise RuntimeError(f"{key} specification changed")
    pr = live_candidate(config, request)
    if pr["state"] != "OPEN" or pr["isDraft"] or pr["mergeable"] != "MERGEABLE":
        raise RuntimeError("PR is not an open, ready, mergeable candidate")
    for check in pr["statusCheckRollup"] or []:
        if check.get("__typename") == "CheckRun":
            if check.get("status") != "COMPLETED" or check.get("conclusion") not in ("SUCCESS", "NEUTRAL", "SKIPPED"):
                raise RuntimeError("GitHub check is failing or pending")
        elif check.get("state") != "SUCCESS":
            raise RuntimeError("GitHub status is failing or pending")
    print(json.dumps(dict(premerge="PASS", repo=config["repo"], pr=request["pr"],
                         head=request["head_sha"], merge_method=config["merge_method"],
                         note="Coordinator must inspect reports, respect authorization, then merge and verify closure.")))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=HERE / "project.json")
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("request", type=Path)
    p.add_argument("--checkout", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    for name in ("dispatch", "premerge"):
        commands.add_parser(name).add_argument("folder", type=Path)
    for name in ("status", "collect"):
        p = commands.add_parser(name)
        p.add_argument("run")
        if name == "collect":
            p.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    config = read(args.config)
    if hasattr(args, "run") and not re.fullmatch(r"issue-\d+-[a-f0-9]{12}-r\d+", args.run):
        raise ValueError("Invalid run ID")
    if args.command == "prepare":
        prepare(config, args.request, args.checkout.resolve(), args.out.resolve())
    elif args.command == "dispatch":
        dispatch(config, args.folder.resolve())
    elif args.command == "status":
        status(config, args.run)
    elif args.command == "premerge":
        premerge(config, args.folder.resolve())
    elif args.command == "collect":
        collect(config, args.run, args.out.resolve())


if __name__ == "__main__":
    main()
