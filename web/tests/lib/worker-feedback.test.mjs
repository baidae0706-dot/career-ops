import assert from "node:assert/strict";
import { test } from "node:test";
import { createWorkerFeedback, workerIdentity, workerState, workerDetailsLabel, workerBatchSummary } from "../../src/lib/worker-feedback.mjs";

const job = (id, status = "done", title = "Evaluate · FixtureCo", subtitle = "Engineer") => ({ id, title, subtitle, status });
function fixture() {
  const notices = [];
  const timers = new Map();
  let next = 0;
  const feedback = createWorkerFeedback((text) => notices.push(text), {
    schedule(fn, delay) { const id = ++next; timers.set(id, { fn, delay }); return id; },
    cancel(id) { timers.delete(id); },
  });
  return { feedback, notices, timers, flush() { const batch = [...timers.values()]; timers.clear(); batch.forEach(({ fn }) => fn()); } };
}

test("task identity includes role; detail names exclude ticking progress", () => {
  const task = { ...job("a", "running"), steps: ["WebFetch"], elapsed: 1 };
  assert.equal(workerIdentity(task), "Evaluate · FixtureCo · Engineer");
  assert.equal(workerIdentity({ title: "Draft CV" }), "Draft CV");
  assert.equal(workerDetailsLabel(task), "打开任务：Evaluate · FixtureCo · Engineer — 运行中");
  assert.equal(workerDetailsLabel({ ...task, elapsed: 60, steps: ["Write"] }), workerDetailsLabel(task));
  assert.equal(workerState("done"), "已完成");
  assert.equal(workerState("error"), "失败");
});

test("batch outcomes distinguish failures, active work and unavailable history", () => {
  assert.equal(workerBatchSummary([job("a"), job("b", "error"), job("c", "running")], 4), "1 项运行中，1 项已完成，1 项失败，1 项不可用");
  assert.equal(workerBatchSummary([job("a"), job("b", "error")]), "1 项已完成，1 项失败");
});

test("no initial/history notice; only terminal events schedule feedback", () => {
  const f = fixture();
  assert.deepEqual(f.notices, []);
  f.feedback.push(job("a", "running"));
  assert.equal(f.timers.size, 0);
  f.feedback.push(job("a"));
  f.flush();
  assert.deepEqual(f.notices, ["", "Evaluate · FixtureCo · Engineer：已完成。"]);
});

test("same terminal event is deduplicated across instances and later renders", () => {
  const f = fixture();
  f.feedback.push(job("a")); f.feedback.push(job("a"));
  f.flush(); f.feedback.push(job("a")); f.flush();
  assert.equal(f.notices.length, 2);
  f.feedback.push(job("b", "done", "Evaluate · FixtureCo", "Designer"));
  f.flush();
  assert.equal(f.notices.at(-1), "Evaluate · FixtureCo · Designer：已完成。");
});

test("concurrent outcomes share a fixed window, including mixed success and failure", () => {
  const f = fixture();
  f.feedback.push(job("a"));
  const timer = [...f.timers.keys()][0];
  f.feedback.push(job("b", "error", "Evaluate · FixtureCo", "Designer"));
  assert.deepEqual([...f.timers.keys()], [timer], "new events must not restart or extend the window");
  assert.equal(f.timers.get(timer).delay, 500);
  f.flush();
  assert.deepEqual(f.notices, ["", "Evaluate · FixtureCo · Engineer：已完成。 Evaluate · FixtureCo · Designer：失败。"]);
});

test("large bursts give bounded counts instead of reading every task", () => {
  const f = fixture();
  for (let i = 0; i < 20; i++) f.feedback.push(job(String(i), i % 2 ? "error" : "done"));
  f.flush();
  assert.equal(f.notices.at(-1), "20 项任务：10 项已完成，10 项失败。打开任务历史查看详情。");
});

test("different tasks with identical labels still create separate mutations", () => {
  const f = fixture();
  f.feedback.push(job("a")); f.flush();
  f.feedback.push(job("b")); f.flush();
  assert.deepEqual(f.notices, ["", "Evaluate · FixtureCo · Engineer：已完成。", "", "Evaluate · FixtureCo · Engineer：已完成。"]);
});

test("unmount cancels pending work and ignores late worker events", () => {
  const f = fixture();
  f.feedback.push(job("a")); f.feedback.dispose(); f.flush();
  f.feedback.push(job("b")); f.flush();
  assert.deepEqual(f.notices, [""]);
  assert.equal(f.timers.size, 0);
});
