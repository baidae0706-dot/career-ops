/** @typedef {{ id: string, title: string, subtitle?: string, status: string }} Worker */

/** @param {Pick<Worker, 'title' | 'subtitle'>} job */
export function workerIdentity(job) {
  return [job.title, job.subtitle].filter(Boolean).join(" · ");
}

/** @param {string} status */
export function workerState(status) {
  return status === "done" ? "已完成" : status === "error" ? "失败" : "运行中";
}

/** Stable during timer/tool updates; includes the visible task identity. @param {Worker} job */
export function workerDetailsLabel(job) {
  return `打开任务：${workerIdentity(job)} — ${workerState(job.status)}`;
}

/** @param {Worker[]} jobs @param {number} total */
export function workerBatchSummary(jobs, total = jobs.length) {
  const counts = [
    ["运行中", jobs.filter((j) => j.status === "running").length],
    ["已完成", jobs.filter((j) => j.status === "done").length],
    ["失败", jobs.filter((j) => j.status === "error").length],
    ["不可用", Math.max(0, total - jobs.length)],
  ];
  return counts.filter(([, count]) => count).map(([state, count]) => `${count} 项${state}`).join("，");
}

/**
 * One owner per provider, fed ONLY by live terminal events (never by rendering or
 * history restoration). A fixed window coalesces concurrent completions without
 * postponing feedback indefinitely when more workers keep finishing.
 * @param {(message: string) => void} publish
 * @param {{ schedule?: typeof setTimeout, cancel?: typeof clearTimeout, delay?: number }} options
 */
export function createWorkerFeedback(publish, { schedule = setTimeout, cancel = clearTimeout, delay = 500 } = {}) {
  const seen = new Set();
  /** @type {Worker[]} */
  let pending = [];
  /** @type {ReturnType<typeof setTimeout> | undefined} */
  let timer;
  let disposed = false;
  return {
    /** @param {Worker} job */
    push(job) {
      if (disposed || !["done", "error"].includes(job.status)) return;
      const key = `${job.id}:${job.status}`;
      if (seen.has(key)) return;
      seen.add(key);
      pending.push(job);
      if (timer !== undefined) return;
      // Leave an empty interval even when two different tasks share a title and
      // outcome, so the second event can create a fresh live-region mutation.
      publish("");
      timer = schedule(() => {
        const batch = pending;
        pending = [];
        timer = undefined;
        publish(batch.length <= 3
          ? batch.map((j) => `${workerIdentity(j)}：${workerState(j.status)}。`).join(" ")
          : `${batch.length} 项任务：${workerBatchSummary(batch)}。打开任务历史查看详情。`);
      }, delay);
    },
    dispose() {
      disposed = true;
      if (timer !== undefined) cancel(timer);
      timer = undefined;
      pending = [];
      seen.clear();
    },
  };
}
