# Preserve official upstream ancestry during integration

Official integration tickets use an explicitly reviewed merge commit, while ordinary feature tickets keep squash merges. Squashing an official integration preserves its files but loses the official commits as ancestors of the fork's main branch; retaining the PR branch does not repair that relationship, and a later synchronization would revisit the old integration boundary. Preserving both parents lets each subsequent official synchronization start from the previously integrated upstream history.

The review request binds the merge method and frozen upstream commit. The existing delivery module verifies both candidate ancestors, the permitted repository method, ordered result parents, exact tree and current target containment, including interrupted delivery recovery. This keeps one acceptance and recovery path rather than adding a separate synchronization service. GitHub's exact-head condition does not atomically pin the target base: preflight and post-merge verification detect a changed integration, and a mismatch blocks closure rather than claiming success.

Git synchronization integrates repository history. The official system updater remains a separate installation mechanism that preserves user data and declared local paths; it cannot establish this ancestry contract.
