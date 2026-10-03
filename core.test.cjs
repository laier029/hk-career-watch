const test = require('node:test');
const assert = require('node:assert/strict');
const core = require('./core.js');
const id = 'a'.repeat(24);
const job = {id,origin:'employer',deadline:null};
test('read moves a job and undo restores it', () => {
  assert.equal(core.visible(job,'employer',{},'2026-10-03'),true);
  const read = {[id]:'2026-10-03T08:00:00Z'};
  assert.equal(core.visible(job,'employer',read,'2026-10-03'),false);
  assert.equal(core.visible(job,'read',read,'2026-10-03'),true);
  delete read[id];
  assert.equal(core.visible(job,'employer',read,'2026-10-03'),true);
});
test('explicit expiry hides unread but preserves read history', () => {
  const expired={...job,deadline:'2026-10-02'};
  assert.equal(core.visible(expired,'employer',{},'2026-10-03'),false);
  assert.equal(core.visible(expired,'read',{[id]:'2026-10-03T08:00:00Z'},'2026-10-03'),true);
});
test('export/import round trip and invalid records rejected', () => {
  const read={[id]:'2026-10-03T08:00:00Z'};
  assert.deepEqual(core.parseReadState(JSON.parse(JSON.stringify({version:1,read}))),read);
  for(const value of [null,{}, {version:1,read:[]}, {version:1,read:{bad:'date'}}, {version:1,read:{[id]:'invalid'}}]) assert.throws(()=>core.parseReadState(value));
});
test('unsafe links cannot become clickable', () => {
  assert.equal(core.safeUrl('javascript:alert(1)'),null);
  assert.equal(core.safeUrl('data:text/html,x'),null);
  assert.equal(core.safeUrl('https://example.com/job'),'https://example.com/job');
});
