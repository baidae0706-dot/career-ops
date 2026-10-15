// The main project runner discovers this boundary; Python owns the protocol tests.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

test('delivery protocol preserves ownership, exact acceptance and crash recovery', () => {
  const root = fileURLToPath(new URL('../../', import.meta.url));
  const python = process.platform === 'win32' ? 'python' : 'python3';
  const result = spawnSync(python, ['scripts/delivery/run_tests.py'], {
    cwd: root, encoding: 'utf8', timeout: 120000,
  });
  assert.equal(result.error, undefined, result.error?.message);
  assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
});
