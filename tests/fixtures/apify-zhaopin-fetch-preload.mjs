// Test transport only. The actual scanner and runner still execute as processes.
import fs from 'node:fs';
import { isMainModule } from '../../lib/is-main-module.mjs';
const scannerIsMain = isMainModule(new URL('../../scan.mjs', import.meta.url).href);
if (process.env.SCAN_COMPAT_AUDIT && scannerIsMain) {
  fs.appendFileSync(process.env.SCAN_COMPAT_AUDIT, JSON.stringify({ pid: process.pid, argv: process.argv.slice(1), overlay: fs.readFileSync(process.env.CAREER_OPS_PORTALS, 'utf8') }) + '\n');
}
if (scannerIsMain) {
if (process.env.SCAN_COMPAT_FAIL === '1') throw new Error('Synthetic scanner startup failure');
let step = 0;
globalThis.fetch = async (url, init = {}) => {
  const u = new URL(url);
  if (u.origin !== 'https://api.apify.com' || init.headers?.authorization !== 'Bearer fixture-token' || u.searchParams.has('token')) throw new Error('Unexpected test egress or authentication');
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
