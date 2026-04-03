const test = require('node:test');
const assert = require('node:assert/strict');

const { normalizeIVIndicatorPayload } = require('./server');

test('normalizeIVIndicatorPayload keeps full new fields', () => {
  const payload = normalizeIVIndicatorPayload({
    civ: 22.5,
    civ_ma5: 22.1,
    civ_pb: 40.0,
    price_pb: 66.0,
    pb_minus_civ_pb: 26.0,
    signal: 26.0,
    dte: 7,
    valid_call_iv_count: 2,
    current_dt: '2026-03-27T09:30:00',
    timestamp: '2026-03-27T09:30:00'
  });

  assert.deepEqual(payload, {
    civ: 22.5,
    civ_ma5: 22.1,
    civ_pb: 40.0,
    price_pb: 66.0,
    pb_minus_civ_pb: 26.0,
    signal: 26.0,
    dte: 7,
    valid_call_iv_count: 2,
    current_dt: '2026-03-27T09:30:00',
    timestamp: '2026-03-27T09:30:00'
  });
});

test('normalizeIVIndicatorPayload backfills pb_minus_civ_pb and time from legacy payload', () => {
  const payload = normalizeIVIndicatorPayload({
    civ: 20.0,
    signal: 11.2,
    timestamp: '2026-03-27T10:00:00'
  });

  assert.equal(payload.pb_minus_civ_pb, 11.2);
  assert.equal(payload.signal, 11.2);
  assert.equal(payload.current_dt, '2026-03-27T10:00:00');
  assert.equal(payload.timestamp, '2026-03-27T10:00:00');
  assert.equal(payload.civ_ma5, null);
  assert.equal(payload.valid_call_iv_count, null);
});
