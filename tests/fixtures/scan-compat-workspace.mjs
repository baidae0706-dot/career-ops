import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { spawnSync } from 'node:child_process';
import * as yaml from 'js-yaml';
export const CODE = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
export const preload = pathToFileURL(path.join(CODE, 'tests/fixtures/apify-zhaopin-fetch-preload.mjs')).href;
export const actorInput = { cityId: '831', maxResults: 0, nested: { flags: [false, 0, 'fixture'] } };
export const items = [
  { title: 'Engineer allowed', company: 'Allow Co', portalUrl: 'http://www.zhaopin.com/jobdetail/CC1.htm', description: '<p>Rust duties and requirements. '.repeat(4) + '</p>' },
  { title: 'Engineer blocked', company: 'Block Co', portalUrl: 'http://www.zhaopin.com/jobdetail/CC2.htm', description: '<p>Forbidden duties and requirements. '.repeat(4) + '</p>' },
  { title: 'Engineer short', company: 'Short Co', portalUrl: 'http://www.zhaopin.com/jobdetail/CC3.htm', description: '<p>Forbidden</p>' },
  { title: 'Engineer unsafe', company: 'Unsafe Co', portalUrl: 'http://other.invalid/job/4', description: 'Rust duties. '.repeat(10) },
];
export function workspace(kind = 'local') {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'career-scan-compat-'));
  for (const dir of ['data', 'config', 'cwd']) fs.mkdirSync(path.join(root, dir));
  const entry = kind === 'apify'
    ? { name: 'Fixture', provider: 'apify', actor: 'fixture/zhaopin', input: actorInput, field_map: { title: 'title', url: 'portalUrl', company: 'company', description: 'description' } }
    : { name: 'Fixture', parser: { command: 'node', script: 'tests/fixtures/scheduled-scan-provider.mjs' } };
  const config = { title_filter: { positive: ['Engineer'] }, max_posting_age_days: 1, content_filter: { negative: ['Forbidden'] }, tracked_companies: [entry] };
  fs.writeFileSync(path.join(root, 'portals.yml'), '# source comments and formatting must remain byte-identical\n' + yaml.dump(config));
  fs.writeFileSync(path.join(root, 'config/plugins.yml'), 'plugins:\n  apify:\n    enabled: true\n');
  fs.writeFileSync(path.join(root, 'config/profile.yml'), '{}\n');
  fs.writeFileSync(path.join(root, 'data/applications.md'), '| # | Date | Company | Role | Score | Status | PDF | Report | Notes |\n|---|---|---|---|---|---|---|---|---|\n');
  fs.writeFileSync(path.join(root, 'data/pipeline.md'), '# Pipeline\n\n');
  return root;
}
export function childEnv(root) {
  const env = {};
  for (const key of ['PATH', 'Path', 'SystemRoot', 'WINDIR', 'ComSpec', 'PATHEXT', 'TEMP', 'TMP', 'USERPROFILE', 'LOCALAPPDATA']) if (process.env[key]) env[key] = process.env[key];
  return { ...env, CAREER_OPS_ROOT: root, CAREER_OPS_CODE_ROOT: CODE, CAREER_OPS_PORTALS: path.join(root, 'portals.yml'), CAREER_OPS_PROFILE: path.join(root, 'config/profile.yml'), CAREER_OPS_TRACKER: path.join(root, 'data/applications.md'), CAREER_OPS_PIPELINE: path.join(root, 'data/pipeline.md'), CAREER_OPS_SCAN_HISTORY: path.join(root, 'data/scan-history.tsv'), CAREER_OPS_SCHEDULED_JOBS_PATH: path.join(root, 'data/scheduled-jobs.json'), APIFY_TOKEN: 'fixture-token', SCAN_COMPAT_ITEMS: JSON.stringify(items), SCAN_COMPAT_AUDIT: path.join(root, 'audit.jsonl'), SCAN_COMPAT_REQUESTS: path.join(root, 'requests.jsonl'), NODE_OPTIONS: `--import=${preload}`, NEXT_TELEMETRY_DISABLED: '1' };
}
export function cli(root, script, args = [], extra = {}) {
  const result = spawnSync(process.execPath, [path.join(CODE, script), ...args], { cwd: path.join(root, 'cwd'), env: { ...childEnv(root), ...extra }, encoding: 'utf8', timeout: 60000, maxBuffer: 8 * 1024 * 1024, windowsHide: true });
  if (result.error || result.signal) throw result.error || new Error(`Killed by ${result.signal}`);
  return result;
}
export const read = (root, p) => fs.readFileSync(path.join(root, p), 'utf8');
export const clean = (root) => fs.rmSync(root, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 });
