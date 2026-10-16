// Test transport only. The actual scanner and runner still execute as processes.
import fs from 'node:fs';
import path from 'node:path';
if (process.env.SCAN_COMPAT_AUDIT && path.basename(process.argv[1] || '') === 'scan.mjs') {
  fs.appendFileSync(process.env.SCAN_COMPAT_AUDIT, JSON.stringify({ pid: process.pid, argv: process.argv.slice(1), overlay: fs.readFileSync(process.env.CAREER_OPS_PORTALS, 'utf8') }) + '\n');
}
if (path.basename(process.argv[1] || '') === 'scan.mjs') {
let step = 0;
globalThis.fetch = async (url, init = {}) => {
  const u = new URL(url);
  if (u.origin !== 'https://api.apify.com' || init.headers?.authorization !== 'Bearer fixture-token' || u.searchParams.has('token')) throw new Error('Unexpected test egress or authentication');
  if (process.env.SCAN_COMPAT_FAIL === '1') return new Response('{}', { status: 400 });
  const expected = ['/v2/acts/fixture~zhaopin/runs', '/v2/actor-runs/fixture-run', '/v2/actor-runs/fixture-run/dataset/items'];
  if (u.pathname !== expected[step]) throw new Error(`Unexpected test request ${u.pathname}`);
  if (step === 0) {
    if (init.method !== 'POST') throw new Error('Expected Actor POST');
    fs.appendFileSync(process.env.SCAN_COMPAT_REQUESTS, JSON.stringify({ path: u.pathname, input: JSON.parse(init.body) }) + '\n');
  }
  const bodies = [{ data: { id: 'fixture-run' } }, { data: { status: 'SUCCEEDED' } }, JSON.parse(process.env.SCAN_COMPAT_ITEMS || '[]')];
  return new Response(JSON.stringify(bodies[step++]), { status: 200 });
};
}
