# Serial delivery

Codex implements one Issue at a time in its isolated worktree. VPS Opus reads an
immutable candidate and independently reviews Standards and Spec. The owning
Codex chat performs reasoning and tool calls; the persistent coordinator supplies
one next action and enforces candidate, ownership and evidence gates. It is not a
background coding service. A thread heartbeat resumes the owner while Codex is
available; an already launched VPS review can finish independently.

The user's recorded authorization for this queue includes specification, ticket
publication, implementation, repair, review, squash merge and Issue closure.
Routine skill confirmation defaults do not interrupt that authorization. It does
not authorize paid job scans, sending applications, deployment, invented career
facts, or changing reference projects. Product confirmations remain required.

## Start or resume

1. Read the current Issue, parent specification and actual blockers in the fork.
   Consult `issue-tracker.md` and `domain.md`. Keep one Issue number as the ticket
   identity; use titles `type(scope): outcome`, branches
   `type/issue-N-clear-description`, and PR titles matching the Issue.
2. Read `local/delivery/state.json` with `coordinator.py show` and ask `next`.
   If absent, initialize once with a queue containing `authorization`,
   `coordinator_thread`, and topologically ordered `issues` objects with `issue`,
   `title`, and `dependencies`. Record the user's authorization source, not a
   guessed permission. Do not import another project's sessions or state.
3. For `claim`, use a unique operation ID and the original Codex thread as owner.
   Repeating the same claim is idempotent; a second writer is rejected. Resume
   repairs in that owner's same worktree and PR. Never reset a dirty shared root.
4. Implement with the agreed public test seams. Run applicable checks, review
   Standards and Spec, commit, push, and create/update the PR with `/pr`'s concise
   Summary, Evidence, and Merge Danger. Record before/after evidence honestly.
   Attach created PRs to the Codex chat. Do not put `Closes #N` in the PR body:
   closure follows verified integration, not GitHub's automatic merge callback.
5. Create a request JSON with all fields in `scripts/delivery/request.example.json`.
   Resolve full base, head and target-base SHA values; the target base must be an
   ancestor of head. Include every acceptance criterion and bounded check argv
   with its actual host. Register it with `candidate --owner ORIGINAL_THREAD`.
6. Run `delivery.py prepare`, persist `coordinator.py intent --kind review`, then
   `delivery.py dispatch`. The same run ID/payload resumes partial upload. A lost
   launch ACK never authorizes a second round. Read original status and reconcile
   it. A missing PID alone is not proof of an unstarted process. An unresolved
   launch intent remains pending until original-process evidence is established.
7. Poll original `status` at reasonable intervals. Only `completed`/`error` with
   both worker and model stopped can be `collect`ed into a fresh directory. Keep
   failed receipts and raw streams. Register the collection with `review`.
8. `CHANGES_REQUIRED` returns to the same implementation owner. A changed head,
   target base, spec or check command requires a new round and acceptance; old
   PASS is never transferable. Infrastructure failure is separate from findings.
   For quota, record the CLI's actual reset timestamp and log using `retry`;
   do not inspect credential files, probe quota APIs, or switch models for quota.
9. If a substantive dispute remains, register a Fable request for the same
   candidate with `--escalation-reason`. Opus and Fable keep separate sessions.
   An invoked Fable must also pass the eventual candidate, and Opus remains the
   final required review. Resume each model's original session after repair.
10. Record Codex's acceptance with `accept`; it binds every criterion and finding
    to the exact Opus request. `next` reaches `merge` only after both accept and
    any invoked Fable passes. Use `coordinator.py merge --issue N`; it rechecks
    receipts, live GitHub spec/head/base/readiness/CI, then squash-merges the exact
    head through one GitHub REST merge mutation without admin bypass. It verifies
    the merge's single parent and tree,
    adds one acceptance comment and confirms Issue closure before advancing.

All commands accept `--config`; coordinator commands accept `--state` and optional
`--revision` for compare-and-set decisions. The default config is project local;
state defaults to ignored `local/delivery/state.json`. Keep round receipts outside
the candidate or within ignored `local/`. Example command sequence:

```text
python scripts/delivery/coordinator.py init QUEUE.json
python scripts/delivery/coordinator.py claim --issue N --owner THREAD --operation claim-N
python scripts/delivery/coordinator.py candidate REQUEST.json --checkout WORKTREE --owner THREAD
python scripts/delivery/delivery.py prepare REQUEST.json --checkout WORKTREE --out NEW_ROUND
python scripts/delivery/coordinator.py intent --kind review --operation issue-N-review-rR
python scripts/delivery/delivery.py dispatch NEW_ROUND
python scripts/delivery/delivery.py status issue-N-HEAD12-rR
python scripts/delivery/delivery.py collect issue-N-HEAD12-rR --out NEW_RECEIPT
python scripts/delivery/coordinator.py review NEW_RECEIPT
python scripts/delivery/coordinator.py accept CODEX_ACCEPTANCE.json --owner THREAD
python scripts/delivery/coordinator.py merge --issue N
python scripts/delivery/coordinator.py next
```

## Recovery and evidence

The coordinator holds an OS lock while it reads and replaces state. State includes
its revision, operation intents, original owner, model sessions, immutable receipt
digests and an event history. Do not delete locks to bypass a live owner. Timeouts
stop only this task's process group/tree; cleanup failure writes a blocking marker.
The VPS worker lock is inherited by checks and model processes, so a dead parent
does not permit a competing reviewer while its children remain alive.

For `reconcile`, inspect the recorded operation. A review resumes the same run ID;
a merge reruns `merge --issue N`, which reads actual PR/merge/comment/closure
state. The finish journal lives beside the immutable review receipt. A provably
unsubmitted or explicitly rejected single-request mutation can retry normally.
For an unknown merge or closure, use `merge --issue N --reconcile-operation merge`
or `close`; this repeats the idempotent mutation only after rechecking the same
candidate and live gates. An unknown comment is only recovered by positive,
complete readback, never resent. A timeout alone proves no outcome. A cleanup
marker blocks recovery until the original process tree is confirmed stopped;
deleting the marker alone is not recovery evidence. Retain evidence and retry;
never label an unknown action successful or launch a replacement blindly.

Receipt verification pins repo, Issue/parent spec, PR, full head/base/target base,
check commands and hosts, actual parent/child model IDs, session, both completed
review axes, skill-load evidence, and artifact hashes. Windows and Linux checks
are independent. A version configured as expected is not proof that it ran.
Neither a unit test nor a heartbeat registration proves full unattended delivery.
The first live review/merge/close provides that separate integration evidence.

Install the reviewed tooling under the configured VPS `remote_root/tools`, outside
the review checkout, only when no worker/child is active. Record file hashes,
Python/Git/gh/Claude versions and the installed review skill hash. Keep the normal
CLI authentication; no credential copying. The worker reads user settings only,
disables hooks and MCP, and exposes read/search/independent-agent/skill tools.
It cannot intentionally edit the candidate; before/after Git checks still apply.

## Verification

Run `python scripts/delivery/run_tests.py` and
`git diff --check`. Tests use temporary repositories and fake GitHub responses at
the external command boundary, never real merges. Process timeout and lock tests
use real OS behavior; the Linux lock test explicitly skips on Windows. A sandbox
that blocks Windows `taskkill` cannot supply Windows process-tree acceptance;
run that check with the authorized task's own process permissions and record it.

This tooling derives from the OhMyShuttle delivery protocol and adds Career Ops
queue state, dispatch recovery and verified completion. Source is reused; reviews,
sessions, approval and test results from those projects are never reused.
