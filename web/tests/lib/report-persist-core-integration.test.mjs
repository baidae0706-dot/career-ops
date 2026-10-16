// Real core subprocesses and scratch data; no model, browser or PDF renderer.
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdtempSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { persistEvaluation } from "../../src/lib/report-persist.mjs";

const CODE_ROOT = dirname(dirname(dirname(dirname(fileURLToPath(import.meta.url)))));
const REPORT = `# Evaluation: Integration Fixture — Engineer

**URL:** https://example.invalid/jobs/integration

## Machine Summary
\`\`\`yaml
company: "Integration Fixture"
role: "Engineer"
score: 4.2
via: null
\`\`\`

## Job Description (archived verbatim)
A synthetic offline job description.
`;

test("web report persistence runs real allocator, writer, tracker merge and release", async () => {
  const root = mkdtempSync(join(tmpdir(), "career-ops-web-core-"));
  const children = [];
  const calls = [];
  const env = Object.fromEntries(Object.entries(process.env).filter(([key]) => !key.startsWith("CAREER_OPS_")));
  env.CAREER_OPS_ROOT = root;
  env.CAREER_OPS_TRACKER = join(root, "data", "applications.md");
  // Keep the official orchestration unchanged. The launcher resolves its three
  // real CLI programs from this checkout while every data path stays in root.
  const spawnFn = (execPath, args, options) => {
    const script = basename(args[0]);
    assert.ok(["reserve-report-num.mjs", "persist-evaluation-report.mjs", "merge-tracker.mjs"].includes(script));
    assert.equal(options.cwd, root);
    calls.push([script, ...args.slice(1)]);
    const child = spawn(execPath, [join(CODE_ROOT, script), ...args.slice(1)], { ...options, env });
    children.push(child);
    return child;
  };
  try {
    mkdirSync(join(root, "data"));
    writeFileSync(env.CAREER_OPS_TRACKER, "# Applications\n\n| # | Date | Company | Role | Score | Status | PDF | Report | Notes | URL |\n|---|---|---|---|---|---|---|---|---|---|\n");
    const result = await persistEvaluation({ spawnFn, execPath: process.execPath, root,
      markdown: REPORT, url: "https://example.invalid/jobs/integration", today: "2026-10-16" });
    assert.equal(result.ok, true, result.error);
    assert.equal(result.num, "001");
    assert.equal(readFileSync(join(root, "reports", result.reportFile), "utf8"), REPORT);
    const tracker = readFileSync(env.CAREER_OPS_TRACKER, "utf8");
    assert.equal(tracker.split("\n").filter((line) => /\|\s*1\s*\|/.test(line)).length, 1, tracker);
    assert.match(tracker, /Integration Fixture/);
    assert.match(tracker, /4\.2\/5/);
    assert.match(tracker, /Evaluated/);
    assert.ok(tracker.includes(`../reports/${result.reportFile}`), tracker);
    assert.ok(tracker.includes("https://example.invalid/jobs/integration"), tracker);
    assert.equal(readdirSync(join(root, "reports")).some((name) => name.endsWith("-RESERVED.md")), false);
    assert.deepEqual(calls, [["reserve-report-num.mjs"], ["persist-evaluation-report.mjs"],
      ["merge-tracker.mjs"], ["reserve-report-num.mjs", "--release", "001"]]);
    assert.ok(children.every((child) => child.exitCode === 0));
    assert.ok(readdirSync(join(root, "batch", "tracker-additions", "merged")).some((name) => name.endsWith(".tsv")));
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
