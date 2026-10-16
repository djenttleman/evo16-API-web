const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const scale = vm.runInNewContext(fs.readFileSync(`${__dirname}/gain-scale.js`, 'utf8') + '; GainScale');

test('UI 0 preserves the old -8 command; UI 50 stays within the confirmed wire range', () => {
  assert.equal(scale.min, 0);
  assert.equal(scale.max, 50);
  assert.equal(scale.toApi(0), -8);
  assert.equal(scale.toApi(0) + 8, 0);
  assert.equal(scale.toApi(50) + 8, 50);
});

test('all confirmed control values round trip through the unchanged API encoding', () => {
  for (let gain = 0; gain <= 50; gain++) {
    assert.equal(scale.toApi(gain) + 8, gain);
    assert.equal(scale.fromApi(scale.toApi(gain)), gain);
  }
  assert.equal(scale.fromApi(-8), 0);
  assert.equal(scale.fromApi(0), 8);
  assert.equal(scale.fromApi(50), 50);
});

test('out-of-range UI writes and invalid reads are rejected', () => {
  for (const value of [-8, -1, 51, 0.5, NaN, Infinity]) assert.throws(() => scale.toApi(value));
  for (const value of [null, undefined, NaN, Infinity]) assert.throws(() => scale.fromApi(value));
});
