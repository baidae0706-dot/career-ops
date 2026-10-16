# Issue tracker

Specs and implementation tickets for this fork live in GitHub Issues at
`baidae0706-dot/career-ops`. Use `gh` with an explicit `--repo` for issue and PR
operations. The official repository is an upstream reference, not this fork's
task destination.

- Read a ticket: `gh issue view NUMBER --repo baidae0706-dot/career-ops`.
- Publish an approved spec or ticket with `gh issue create --repo baidae0706-dot/career-ops --title TITLE --body-file PATH`.
- Open implementation PRs against this fork's `main`, using a body file.
- Link tickets to their parent spec and record actual blocking dependencies.
- Apply `ready-for-agent` only when scope, acceptance criteria, and dependencies are settled.
- Keep PRs as an incoming triage surface disabled.

## Upstream and local changes

`origin` is the personal fork; `upstream` is the official repository. Preserve
existing uncommitted work before integration. Sync upstream changes on a separate
branch and validate before merging into the fork's `main`. The built-in system
updater is not a substitute for Git merge: it can skip locally modified system
files and does not synchronize the complete repository.
