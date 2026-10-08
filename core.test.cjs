const test=require('node:test'),assert=require('node:assert/strict'),C=require('./core.js');
const id='a'.repeat(24),id2='b'.repeat(24),date='2026-10-08T00:00:00Z';
const job={id,track:'supply',category:'daily',state:'active',first_seen:'2026-10-01T00:00:00Z',role_tags:['procurement'],company:'A',title:'Intern',sources:[]};
const f={track:'supply',tab:'pending',tags:[]};
test('read hides, important change resurfaces and ack clears',()=>{
 let state=C.action(C.empty(),[id],'read_at',date);
 assert.equal(C.matches(job,f,state,'2026-10-08',''),false);
 const changed={...job,changed_at:'2026-10-09T00:00:00Z'};
 assert.equal(C.matches(changed,f,state,'2026-10-09',''),true);
 state=C.action(state,[id],'read_at','2026-10-10T00:00:00Z');assert.equal(C.matches(changed,f,state,'2026-10-10',''),false);
});
test('saved and applied survive expiry, export/import',()=>{
 let state=C.action(C.empty(),[id],'saved_at',date);state=C.action(state,[id],'applied_at',date);
 assert.equal(C.matches({...job,state:'archived'},{...f,tab:'saved'},state,'2026-10-08',''),true);
 assert.equal(C.matches({...job,state:'archived'},{...f,tab:'applied'},state,'2026-10-08',''),true);
 assert.deepEqual(C.parseState(JSON.parse(JSON.stringify(state))),state);
});
test('v1 backup and unique ID migration',()=>{
 const old=C.parseState({version:1,read:{[id]:date}}),out=C.migrate(old,[{id:id2,legacy_ids:[id]}]);
 assert.equal(out.state.jobs[id2].read_at,date);assert.equal(out.state.jobs[id],undefined);
 const ambiguous=C.migrate(old,[{id:id2,legacy_ids:[id]},{id:'c'.repeat(24),legacy_ids:[id]}]);assert.equal(ambiguous.ambiguous,1);assert.ok(ambiguous.state.jobs[id]);
});
test('unmatched and other-tab data retained by combine',()=>{
 const a=C.action(C.empty(),[id],'saved_at',date),b=C.action(C.empty(),[id2],'read_at',date);
 assert.equal(Object.keys(C.combine(a,b).jobs).length,2);
});
test('invalid and unsafe input rejected',()=>{
 for(const v of [null,{}, {version:2,jobs:[]},{version:2,jobs:{[id]:{read_at:'bad'}}},{version:2,jobs:{[id]:{url:date}}}])assert.throws(()=>C.parseState(v));
 assert.equal(C.safeUrl('javascript:alert(1)'),null);
});
test('selected-only bulk action and undo snapshot',()=>{
 const before=C.action(C.empty(),[id2],'saved_at',date),after=C.action(before,[id],'read_at',date);
 assert.equal(after.jobs[id2].read_at,undefined);assert.equal(before.jobs[id],undefined);
 assert.deepEqual(C.parseState(before),before);
});
test('review separated and old unread backlog kept',()=>{
 assert.equal(C.matches(job,f,C.empty(),'2026-10-08',date),true);
 assert.equal(C.matches({...job,state:'review'},f,C.empty(),'2026-10-08',date),false);
 assert.equal(C.matches({...job,state:'review'},{...f,tab:'review'},C.empty(),'2026-10-08',date),true);
});
test('new then deadline then older unread ordering',()=>{
 const jobs=[job,{...job,id:id2,deadline:'2026-10-09'},{...job,id:'c'.repeat(24),first_seen:'2026-10-08T01:00:00Z'}];
 assert.deepEqual(C.sort(jobs,C.empty(),'2026-10-08',date).map(j=>j.id),['c'.repeat(24),id2,id]);
});
