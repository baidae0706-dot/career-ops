import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import * as yaml from 'js-yaml';
import { workspace, cli, read, clean, actorInput } from './fixtures/scan-compat-workspace.mjs';

test('real scanner applies converted descriptions and writes/reuses the data-root JD', () => {
  const root = workspace('apify');
  const original = read(root, 'portals.yml');
  try {
    const first = cli(root, 'scan.mjs', ['--json', '--quiet']);
    assert.equal(first.status, 0, first.stderr);
    const receipt = JSON.parse(first.stdout);
    assert.equal(receipt.added, 1);
    const pipeline = read(root, 'data/pipeline.md');
    assert.match(pipeline, /Engineer allowed/);
    assert.doesNotMatch(pipeline, /Engineer blocked|Engineer short|Engineer unsafe/);
    const cache = fs.readdirSync(path.join(root, 'jds'));
    assert.equal(cache.length, 2, 'all long valid bodies cache before scanner filters');
    const body = read(root, 'jds/' + cache.find((p) => p.includes('allow-co')));
    assert.match(body, /url: "https:\/\/www.zhaopin.com\/jobdetail\/CC1.htm"/);
    assert.match(body, /Rust duties/);
    assert.doesNotMatch(body, /<p>/);
    const request = JSON.parse(read(root, 'requests.jsonl').trim());
    assert.deepEqual(request.input, actorInput);
    const second = cli(root, 'scan.mjs', ['--json', '--quiet']);
    assert.equal(second.status, 0, second.stderr);
    assert.equal(JSON.parse(second.stdout).added, 0);
    assert.deepEqual(fs.readdirSync(path.join(root, 'jds')), cache);
    assert.equal(read(root, 'portals.yml'), original);
    assert.equal(fs.existsSync(path.join(root, 'cwd/jds')), false);
  } finally { clean(root); }
});

test('real scanner retains unknown dates but applies official known-date bounds', () => {
  const root = workspace();
  try {
    const result = cli(root, 'scan.mjs', ['--json', '--quiet', '--since', '7']);
    assert.equal(result.status, 0, result.stderr);
    assert.equal(JSON.parse(result.stdout).added, 4);
    const pipeline = read(root, 'data/pipeline.md');
    for (const key of ['fresh', 'unknown', 'invalid', 'scraped']) assert.match(pipeline, new RegExp('/' + key));
    assert.doesNotMatch(pipeline, /\/old/);
    const invalid = cli(root, 'scan.mjs', ['--since', '0']);
    assert.notEqual(invalid.status, 0);
    assert.match(invalid.stderr, /positive number/);
  } finally { clean(root); }
});

for (const days of [0, 7, '0']) test(`real runner keeps numeric portals0 distinct (${JSON.stringify(days)})`, () => {
  const root = workspace();
  const original = read(root, 'portals.yml');
  const job = { createdAt: new Date().toISOString(), updatedAt: new Date().toISOString(), id: '11111111-1111-4111-8111-111111111111', name: 'Fixture', status: 'active', engine: 'portals', filters: { sinceDays: days, positive: ['Engineer'] }, timezone: 'UTC', startAt: '2099-01-01T00:00:00.000Z', nextRunAt: '2099-01-01T00:00:00.000Z', every: 1, unit: 'hours' };
  fs.writeFileSync(path.join(root, 'data/scheduled-jobs.json'), JSON.stringify({ jobs: [job], runs: [], queue: [] }));
  try {
    const result = cli(root, 'web/scripts/scheduled-jobs-runner.mjs', ['--job', job.id]);
    assert.equal(result.status, 0, result.stderr);
    const summary = JSON.parse(result.stdout);
    assert.equal(summary.rolesFound, days === 0 ? 5 : 4);
    const audit = JSON.parse(read(root, 'audit.jsonl').trim());
    assert.equal(audit.argv.includes('--since'), days !== 0);
    const overlay = yaml.load(audit.overlay);
    assert.equal('max_posting_age_days' in overlay, days !== 0);
    assert.equal(read(root, 'portals.yml'), original);
    assert.deepEqual(fs.readdirSync(path.join(root, 'data/tmp')), []);
    const idle = cli(root, 'web/scripts/scheduled-jobs-runner.mjs');
    assert.equal(idle.status, 0, idle.stderr);
    assert.equal(JSON.parse(idle.stdout).status, 'idle');
    const persisted = JSON.parse(read(root, 'data/scheduled-jobs.json'));
    assert.equal(persisted.jobs[0].filters.sinceDays, days);
    assert.equal(persisted.runs[0].state, 'success');
    assert.equal(persisted.queue.length, 0);
  } finally { clean(root); }
});


test('real runner cleans every failed scanner startup without changing source input', () => {
  const root = workspace('apify');
  const original = read(root, 'portals.yml');
  const id = '11111111-1111-4111-8111-111111111111';
  const at = new Date().toISOString();
  const job = { id, name: 'Failure', status: 'active', engine: 'portals', filters: { sinceDays: 0, positive: ['Engineer'] }, timezone: 'UTC', startAt: at, createdAt: at, updatedAt: at, every: 1, unit: 'hours' };
  fs.writeFileSync(path.join(root, 'data/scheduled-jobs.json'), JSON.stringify({ jobs: [job], runs: [], queue: [] }));
  try {
    const result = cli(root, 'web/scripts/scheduled-jobs-runner.mjs', ['--job', id], { SCAN_COMPAT_FAIL: '1' });
    assert.notEqual(result.status, 0);
    assert.equal(read(root, 'portals.yml'), original);
    const audits = read(root, 'audit.jsonl').trim().split('\n').map(JSON.parse);
    assert.equal(audits.length, 3);
    for (const audit of audits) {
      assert.equal(audit.argv.includes('--since'), false);
      const overlay = yaml.load(audit.overlay);
      assert.equal('max_posting_age_days' in overlay, false);
      assert.deepEqual(overlay.tracked_companies[0].input, actorInput);
    }
    assert.deepEqual(fs.readdirSync(path.join(root, 'data/tmp')), []);
    assert.equal(JSON.parse(read(root, 'data/scheduled-jobs.json')).runs[0].state, 'failed');
  } finally { clean(root); }
});
