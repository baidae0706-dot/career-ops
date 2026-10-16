# Domain documents

Use a single context: `GLOSSARY.md` at the repository root and decisions under
`docs/adr/`. Read the existing glossary and relevant ADRs before requirements,
architecture, or implementation work. Missing documents do not block exploration;
create them only when a term or a durable decision has been resolved.

Use the glossary's defined terms in specs, tickets, and implementation discussions.
If a proposal conflicts with an existing ADR, identify the ADR and explain why the
decision should be revisited before proceeding.

A complete WebUI workflow lets the user provide inputs, start work, observe
progress, handle required confirmations, inspect or export results, and recover
from failure without manually using a terminal. The backend can use existing
Career Ops scripts and AI CLIs. A command-copy button or generic chat entry alone
does not establish workflow coverage.

Follow `DATA_CONTRACT.md` and `web/AGENTS.md` when connecting workflows to core.
