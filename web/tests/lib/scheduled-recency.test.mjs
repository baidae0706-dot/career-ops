import test from 'node:test';
import assert from 'node:assert/strict';
import { scheduledSinceDays } from '../../src/lib/scheduled-recency.mjs';
test('saved scheduled exception is numeric portals zero only', () => {
  assert.equal(scheduledSinceDays('portals', { sinceDays: 0, since: 14 }, 1), 0);
  assert.equal(scheduledSinceDays('portals', { since: 0 }, 1), 0);
  assert.equal(scheduledSinceDays('portals', { sinceDays: 14, since: 0 }, 14), 14);
  assert.equal(scheduledSinceDays('portals', { sinceDays: '0' }, 1), 1);
  assert.equal(scheduledSinceDays('portals', {}, 0), 0);
  assert.equal(scheduledSinceDays('full', {}, 0), 7);
  assert.equal(scheduledSinceDays('full', { sinceDays: 0 }, 1), 1);
});
