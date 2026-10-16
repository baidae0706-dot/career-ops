// Optional browser regression for the real JobsProvider -> persisted steps ->
// WorkerCard/detail path. Start the app against tests/fixtures/pipeline-status.mjs
// and set JOBS_RECOVERY_TEST_URL/ROOT. All run/CLI APIs below are fictional stubs;
// no real CLI/model, CV generation or external service is invoked.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import http from "node:http";
import { test } from "node:test";
import { jobErrorHint } from "../../src/lib/job-error-hint.mjs";

const url = process.env.JOBS_RECOVERY_TEST_URL;
const root = process.env.JOBS_RECOVERY_TEST_ROOT;
const out = process.env.JOBS_RECOVERY_TEST_OUT;

test("JobsProvider keeps terminal causes canonical while showing Chinese recovery guidance", { skip: !url || !root, timeout: 60_000 }, async (t) => {
  const origin = new URL(url);
  assert.ok(["localhost", "127.0.0.1", "[::1]"].includes(origin.hostname));
  const relative = path.relative(os.tmpdir(), fs.realpathSync(root));
  assert.ok(relative && !relative.startsWith("..") && !path.isAbsolute(relative));
  assert.equal(fs.readFileSync(path.join(root, ".inline-status-fixture"), "utf8").trim(), "fictional-only");
  const tracker = fs.readFileSync(path.join(root, "data/applications.md"), "utf8");
  const { chromium } = await import("playwright-core");
  const browser = await chromium.launch({ channel: process.env.CAREER_OPS_TEST_BROWSER_CHANNEL || "chrome", headless: true });
  t.after(() => browser.close());
  if (out) fs.mkdirSync(out, { recursive: true });

  const cases = [
    { name: "unconfigured", kind: "auth", raw: "No CLI configured — open Config and click Save config", display: "尚未配置 CLI，请打开“设置”并点击“保存设置”", hint: "请在“设置”中登录你的 CLI，然后重新运行。" },
    { name: "connection", kind: "connection", raw: "Connection error", display: "连接错误", hint: "与本地服务器的连接已断开，请重新运行。" },
    { name: "reload", kind: "interrupted", raw: "Interrupted (page reloaded)", display: "已中断（页面已刷新）", hint: "任务已中断，请重新运行。" },
  ];
  for (const c of cases) await t.test(c.name, async () => {
    const context = await browser.newContext({ viewport: { width: 1365, height: 1000 } });
    const page = await context.newPage();
    const posts = [], unexpected = [], errors = [];
    const responses = [];
    const fixture = http.createServer((req, res) => {
      res.writeHead(200, { "Content-Type": "text/event-stream", "Access-Control-Allow-Origin": origin.origin });
      res.flushHeaders();
      responses.push(res); // hold the actual fetch open until page.reload()
    });
    await new Promise((resolve) => fixture.listen(0, "127.0.0.1", resolve));
    try {
      page.on("pageerror", (error) => errors.push(error.message));
      await page.addInitScript((enabled) => localStorage.setItem("career-ops:config", JSON.stringify({ cliId: enabled ? "fixture-cli" : "", logos: false })), c.name !== "unconfigured");
      // Test-only loopback guard. Edge is an explicit Windows channel; the default
      // remains Chrome. Stub discovery/telemetry so neither user settings nor a
      // model can be reached by this real-provider regression.
      await context.route("**/*", (route) => {
        const u = new URL(route.request().url());
        if (u.origin !== origin.origin) { unexpected.push(u.href); return route.abort(); }
        if (!u.pathname.startsWith("/api/")) return route.continue();
        if (u.pathname === "/api/run") {
          posts.push(route.request().postDataJSON());
          if (c.name === "connection") return route.abort("connectionfailed");
          if (c.name === "reload") return route.continue({ url: `http://127.0.0.1:${fixture.address().port}/run` });
          unexpected.push("unconfigured run launched"); return route.abort();
        }
        if (route.request().method() !== "GET") { unexpected.push(u.pathname); return route.abort(); }
        if (u.pathname === "/api/clis") return route.fulfill({ json: { clis: c.name === "unconfigured" ? [] : [{ id: "fixture-cli", installed: true }] } });
        if (u.pathname === "/api/logo") return route.fulfill({ status: 204 });
        return route.fulfill({ json: { available: true, clis: [], chats: [], errors: [], version: "fixture" } });
      });
      await page.goto(`${origin.origin}/pipeline/11`);
      await page.getByRole("button", { name: "打开助手", exact: true }).waitFor();
      await page.getByRole("button", { name: "生成定制简历（PDF）", exact: true }).click();
      const stored = () => page.evaluate(() => JSON.parse(localStorage.getItem("career-ops:jobs") || "[]"));
      async function until(check) {
        for (let i = 0; i < 200; i++) { if (await check()) return; await page.waitForTimeout(25); }
        assert.fail(`JobsProvider ${c.name} did not settle`);
      }
      await until(async () => (await stored()).length === 1);
      if (c.name === "reload") {
        await until(() => responses.length === 1);
        const running = (await stored())[0];
        assert.equal(running.status, "running");
        await page.reload(); // no hand-constructed error job or terminal label
      }
      await until(async () => (await stored())[0]?.status === "error");
      const job = (await stored())[0];
      const hint = jobErrorHint(job); // classifier consumes actual provider output
      console.log(JSON.stringify({ case: c.name, job, hint, posts }));
      if (out) fs.writeFileSync(path.join(out, `${c.name}-raw.json`), JSON.stringify({ job, hint, posts }, null, 2));
      assert.equal(hint?.kind, c.kind);
      assert.equal(job.steps.at(-1).label, c.raw);
      assert.equal(job.steps[0].label, "Starting…");
      assert.equal(job.kind, "pdf");
      assert.equal(job.input, "11");
      assert.equal(job.page, "/pipeline/11");
      assert.deepEqual(posts, c.name === "unconfigured" ? [] : [{ kind: "pdf", input: "11", cliId: "fixture-cli" }]);
      const card = page.getByRole("complementary").locator(`a[href="/jobs/${job.id}"]`);
      await card.getByText(c.display, { exact: true }).waitFor();
      await card.getByText(c.hint, { exact: true }).waitFor();
      await card.click();
      await page.getByRole("heading", { name: job.title, exact: true }).waitFor();
      await page.locator("main ol").getByText(c.display, { exact: true }).waitFor();
      // Navigation persists the same raw cause; render-only translation must
      // never rewrite history to whatever string the UI currently displays.
      assert.deepEqual((await stored())[0], job);
      if (out) {
        await page.screenshot({ path: path.join(out, `${c.name}.png`), fullPage: true, animations: "disabled" });
        fs.writeFileSync(path.join(out, `${c.name}-accessibility.txt`), await page.locator("body").ariaSnapshot());
      }
      assert.deepEqual(unexpected, []);
      assert.deepEqual(errors, []);
      assert.equal(fs.readFileSync(path.join(root, "data/applications.md"), "utf8"), tracker);
    } finally {
      await context.close();
      responses.forEach((res) => res.end());
      fixture.closeAllConnections();
      await new Promise((resolve) => fixture.close(resolve));
    }
  });
});
