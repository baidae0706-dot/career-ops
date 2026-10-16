import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import plugin, { normalizeJobUrl, isHttpsUrl } from '../plugins/apify/index.mjs';

test('only standard Zhaopin HTTP job pages are upgraded to HTTPS', () => {
  const legacy = 'http://www.zhaopin.com/jobdetail/CC181097920J40896713109.htm';
  assert.equal(normalizeJobUrl(legacy), legacy.replace('http:', 'https:'));
  for (const unsafe of [
    'http://other.example/jobdetail/CC1.htm',
    'http://www.zhaopin.com.evil.example/jobdetail/CC1.htm',
    'http://user:password@www.zhaopin.com/jobdetail/CC1.htm',
    'http://www.zhaopin.com:8080/jobdetail/CC1.htm',
    'http://www.zhaopin.com/jobdetail/CC1.htm?redirect=https://evil.example',
    'http://www.zhaopin.com/not-a-job',
    'javascript:alert(1)',
    'file:///C:/private.txt',
  ]) {
    assert.equal(isHttpsUrl(normalizeJobUrl(unsafe)), false, unsafe);
  }
});

test('actor result reaches JD cache and content filters without allowing arbitrary HTTP', async () => {
  const originalFetch = globalThis.fetch;
  const originalCwd = process.cwd();
  const scratch = mkdtempSync(join(tmpdir(), 'career-apify-compat-'));
  const description = 'A public job description with duties and requirements. '.repeat(3);
  const calls = [];
  const responses = [
    { data: { id: 'fixture-run' } },
    { data: { status: 'SUCCEEDED' } },
    [
      { title: 'Quality specialist', company: 'Example', location: 'Example city',
        portalUrl: 'http://www.zhaopin.com/jobdetail/CC181097920J40896713109.htm', description },
      { title: 'Unsafe source', portalUrl: 'http://other.example/job/1', description },
    ],
  ];
  globalThis.fetch = async (url, init) => {
    calls.push({ url, init });
    assert.equal(new URL(url).hostname, 'api.apify.com');
    assert.equal(init.headers.authorization, 'Bearer fixture-token');
    assert.equal(new URL(url).searchParams.has('token'), false);
    assert.ok(responses.length > 0, 'unexpected extra request');
    return new Response(JSON.stringify(responses.shift()), { status: 200 });
  };
  try {
    process.chdir(scratch);
    const jobs = await plugin.provider.fetch({
      name: 'Fixture', actor: 'blackfalcondata/zhaopin-scraper',
      input: { maxResults: 5 },
      field_map: { title: 'title', url: 'portalUrl', company: 'company',
        location: 'location', description: 'description' },
    }, { env: { APIFY_TOKEN: 'fixture-token' } });
    assert.equal(jobs.length, 1);
    assert.equal(jobs[0].description, description.trim());
    assert.match(jobs[0].url, /^local:jds\//);
    assert.match(jobs[0]._remote_url, /^https:\/\/www\.zhaopin\.com\/jobdetail\//);
    const cached = readFileSync(jobs[0].url.slice('local:'.length), 'utf8');
    assert.ok(cached.includes(description.trim()));
    assert.equal(calls.length, 3);
    assert.equal(calls[0].init.method, 'POST');
    assert.deepEqual(JSON.parse(calls[0].init.body), { maxResults: 5 });
  } finally {
    globalThis.fetch = originalFetch;
    process.chdir(originalCwd);
    rmSync(scratch, { recursive: true, force: true });
  }
});

test('URL parser canonicalization remains the saved contract', () => {
  for (const suffix of ['', '?', '#']) assert.equal(normalizeJobUrl('http://www.zhaopin.com:80/jobdetail/CC1.htm' + suffix), 'https://www.zhaopin.com/jobdetail/CC1.htm' + suffix);
  assert.equal(normalizeJobUrl('http://WWW.ZHAOPIN.COM/jobdetail/CC1.htm'), 'https://www.zhaopin.com/jobdetail/CC1.htm');
  assert.equal(isHttpsUrl(normalizeJobUrl('http://www.zhaopin.com/jobdetail/CC1.htm#fragment')), false);
});
