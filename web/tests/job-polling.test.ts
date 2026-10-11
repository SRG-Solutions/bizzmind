import {test} from 'node:test';
import assert from 'node:assert/strict';
import {pollJob,JobCancelled} from '../src/lib/job-polling.ts';

test('background delays and temporary connection errors keep the same job and event cursor',async()=>{
 const seen:number[]=[],cursors:number[]=[],waits:number[]=[];let cancelled=0;
 const answers=[
  {status:'running',events:[{seq:1}]},
  new TypeError('offline'),Object.assign(new Error('unavailable'),{status:503}),
  {status:'running',events:[{seq:1},{seq:2}]},
  {status:'done',events:[{seq:3}],result:{reply:'Done'}},
 ];
 const result=await pollJob({read:async(since)=>{cursors.push(since);const next=answers.shift();if(next instanceof Error)throw next;return next as never;},wait:async(ms)=>{waits.push(ms);},cancel:async()=>{cancelled++;},onEvent:(e:{seq:number})=>seen.push(e.seq)});
 assert.deepEqual(result,{reply:'Done'});assert.deepEqual(seen,[1,2,3]);assert.deepEqual(cursors,[0,1,1,1,2]);assert.equal(cancelled,0);assert.equal(Math.max(...waits),2400);
});
test('only explicit Stop cancels server work',async()=>{
 const controller=new AbortController();let cancelled=0,reads=0;
 await assert.rejects(pollJob({read:async()=>{reads++;return {status:'running',events:[]};},wait:async()=>{controller.abort();},cancel:async()=>{cancelled++;},signal:controller.signal}),JobCancelled);
 assert.equal(cancelled,1);assert.equal(reads,0);
});
test('a finished job is recovered once and failed/cancelled jobs remain terminal',async()=>{
 const wait=async()=>{};let cancels=0;const cancel=async()=>{cancels++;};
 assert.deepEqual(await pollJob({read:async()=>({status:'done',events:[],result:{reply:'Recovered'}}),wait,cancel}),{reply:'Recovered'});
 await assert.rejects(pollJob({read:async()=>({status:'failed',events:[],error:'Could not finish'}),wait,cancel}),/Could not finish/);
 await assert.rejects(pollJob({read:async()=>({status:'cancelled',events:[]}),wait,cancel}),JobCancelled);
 assert.equal(cancels,0);
});
test('authorization/not-found errors stop watching without cancelling or retrying the job',async()=>{
 for(const status of [401,403,404]){
  let reads=0,cancels=0;
  await assert.rejects(pollJob({read:async()=>{reads++;throw Object.assign(new Error('access'),{status});},wait:async()=>{},cancel:async()=>{cancels++;}}),/access/);
  assert.equal(reads,1);assert.equal(cancels,0);
 }
});
