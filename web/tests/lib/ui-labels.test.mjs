import assert from "node:assert/strict";
import { test } from "node:test";
import { uiLabel, employerOutcomeLabel } from "../../src/lib/ui-labels.ts";
import { employerOutcome } from "../../src/lib/employer-preset.mjs";
import { fencingReport } from "../../src/lib/cli-fencing.mjs";
import { CAPS } from "../../src/lib/worker-capabilities.mjs";

test("employer display retains incomplete counts and leaves the canonical outcome untouched", () => {
  const outcome = employerOutcome([
    { id: "tencent", state: "failed", reason: "source timed out" },
    { id: "bytedance", state: "incomplete", reason: "page cap (10 pages) limits coverage" },
    { id: "meituan", state: "complete" },
  ], 7);
  const before = JSON.stringify(outcome);
  const display = employerOutcomeLabel(outcome.message);
  assert.match(display, /扫描未完成.*7 个匹配职位/);
  assert.match(display, /腾讯.*来源超时/);
  assert.match(display, /10 页上限/);
  assert.equal(JSON.stringify(outcome), before);
  assert.equal(outcome.state, "partial");
});

test("failed and successful zero-match employer scans remain distinct in Chinese", () => {
  const failed = employerOutcome([{ id: "tencent", state: "failed", reason: "source stopped early" }], 0);
  const empty = employerOutcome([{ id: "tencent", state: "complete" }], 0);
  assert.match(employerOutcomeLabel(failed.message), /扫描失败.*来源提前停止/);
  assert.match(employerOutcomeLabel(empty.message), /没有匹配职位/);
  assert.doesNotMatch(employerOutcomeLabel(failed.message), /没有匹配职位/);
});

test("unknown source diagnostics and rejected factual claims remain visible", () => {
  const details = "custom source diagnostic XYZ";
  assert.match(employerOutcomeLabel(`Failed — Tencent / 腾讯: ${details}.`), /custom source diagnostic XYZ/);
  const claims = "revenue doubled, 50 reports";
  assert.equal(uiLabel(`The rewrite was discarded because it adds claims this bullet does not support: ${claims}.`), `已舍弃改写，因为它新增了原要点无法支持的陈述： ${claims}.`);
});

test("permission warnings preserve both unrestricted and partly restricted limitations", () => {
  const unrestricted = fencingReport({ cliId: "grok", cliName: "Grok", capabilities: CAPS.localReadOnly });
  assert.match(uiLabel(unrestricted.notice), /Grok 无法施加权限限制.*默认访问权限/);
  const partial = fencingReport({ cliId: "codex", cliName: "Codex", capabilities: { ...CAPS.localReadOnly, network: "fetch" } });
  assert.match(uiLabel(partial.notice), /仅受部分权限限制/);
  assert.match(uiLabel(partial.notice), /并未完全禁止写入/);
  assert.equal(partial.level, "partial");
});
