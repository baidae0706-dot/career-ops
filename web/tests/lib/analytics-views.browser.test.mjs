// Optional live regression: use the disposable pipeline-status fixture and a
// localhost server, then set ANALYTICS_TEST_URL and ANALYTICS_TEST_ROOT.
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { test } from "node:test";

const url = process.env.ANALYTICS_TEST_URL;
const root = process.env.ANALYTICS_TEST_ROOT;

test("Analytics rebase retains Progress, 搜索统计 and core Insights", {
  skip: !url || !root,
  timeout: 120_000,
}, async (t) => {
  const origin = new URL(url);
  assert.ok(["localhost", "127.0.0.1", "[::1]"].includes(origin.hostname));
  const relative = path.relative(os.tmpdir(), fs.realpathSync(root));
  assert.ok(relative && !relative.startsWith("..") && !path.isAbsolute(relative));
  assert.equal(fs.readFileSync(path.join(root, ".inline-status-fixture"), "utf8").trim(), "fictional-only");
  const tracker = path.join(root, "data/applications.md");
  const initial = fs.readFileSync(tracker, "utf8");
  for (const name of ["Fixture Alpha", "Fixture Beta", "Fixture Gamma"]) assert.ok(initial.includes(name));

  const { chromium } = await import("playwright-core");
  const browser = await chromium.launch({ channel: process.env.CAREER_OPS_TEST_BROWSER_CHANNEL || "chrome", headless: true });
  t.after(() => browser.close());
  const page = await browser.newPage();
  await page.context().route("**/api/logo?**", (route) => route.fulfill({ status: 204 }));
  await page.context().route("**/api/usage", (route) => route.fulfill({ json: {} }));
  await page.context().route("**/api/version", (route) => route.fulfill({ json: { version: "fixture" } }));
  await page.addInitScript(() => localStorage.setItem("career-ops:config", JSON.stringify({ ...JSON.parse(localStorage.getItem("career-ops:config") || "{}"), logos: false })));
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const nav = page.getByRole("navigation", { name: "分析视图" });
  for (const query of ["", "?view=progress", "?view=bogus", "?tab=search-stats", "?view=progress&tab=search-stats"]) {
    await t.test(`Progress and core conversion survive ${query || "the default URL"}`, async () => {
      const response = await page.goto(`${origin.origin}/analytics${query}`);
      assert.equal(response.status(), 200);
      await page.getByRole("heading", { name: "申请进展", exact: true }).waitFor();
      await page.getByRole("heading", { name: "转化率", exact: true }).waitFor();
      assert.equal(await nav.getByRole("link", { name: "求职进展", exact: true }).getAttribute("aria-current"), "page");
      assert.deepEqual(await nav.getByRole("link").evaluateAll(links => links.map(link => link.getAttribute("href"))),
        ["/analytics", "/analytics?view=insights", "/analytics?view=search-stats"]);
    });
  }
  await t.test("搜索统计 still renders and links to core Insights", async () => {
    const response = await page.goto(`${origin.origin}/analytics?view=search-stats&tab=progress`);
    assert.equal(response.status(), 200);
    await page.getByRole("heading", { name: "求职策略洞察", exact: true }).waitFor();
    assert.equal(await nav.getByRole("link", { name: "搜索统计", exact: true }).getAttribute("aria-current"), "page");
    assert.equal(await nav.getByRole("link", { name: "洞察", exact: true }).getAttribute("href"), "/analytics?view=insights");
    assert.equal(await page.getByRole("heading", { name: "申请进展", exact: true }).count(), 0);
  });
  await t.test("Insights keeps the core's small-sample message, without Progress requests", async () => {
    const coreRequests = [];
    const track = (request) => {
      const pathname = new URL(request.url()).pathname;
      if (["/api/stats", "/api/patterns"].includes(pathname)) coreRequests.push(pathname);
    };
    page.on("request", track);
    const response = await page.goto(`${origin.origin}/analytics?view=insights&tab=search-stats`);
    assert.equal(response.status(), 200);
    await page.getByText("申请数量还不够", { exact: true }).waitFor();
    assert.equal(await nav.getByRole("link", { name: "洞察", exact: true }).getAttribute("aria-current"), "page");
    assert.ok(coreRequests.includes("/api/patterns"));
    assert.ok(!coreRequests.includes("/api/stats"));
    assert.equal(await page.getByRole("heading", { name: "申请进展", exact: true }).count(), 0);
    page.off("request", track);
  });
  await t.test("view links navigate between all three panels using one query contract", async () => {
    await nav.getByRole("link", { name: "搜索统计", exact: true }).click();
    await page.getByRole("heading", { name: "求职策略洞察", exact: true }).waitFor();
    assert.equal(new URL(page.url()).search, "?view=search-stats");
    await nav.getByRole("link", { name: "求职进展", exact: true }).click();
    await page.getByRole("heading", { name: "申请进展", exact: true }).waitFor();
    assert.equal(new URL(page.url()).search, "");
    await nav.getByRole("link", { name: "洞察", exact: true }).click();
    await page.getByText("申请数量还不够", { exact: true }).waitFor();
    assert.equal(new URL(page.url()).search, "?view=insights");
  });
  assert.deepEqual(errors, []);
  assert.equal(fs.readFileSync(tracker, "utf8"), initial);
});
