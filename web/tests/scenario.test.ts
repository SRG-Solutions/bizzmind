import {test} from 'node:test';
import assert from 'node:assert/strict';
import {calculateScenario,evaluate,type ScenarioSpec} from '../src/lib/scenario.ts';
const model:ScenarioSpec={
 inputs:[{id:'price',label:'Price',value:10,min:0,max:100,step:1}],periods:3,period_label:'Year',
 outputs:[{id:'revenue',label:'Revenue',formula:['mul','price',20]},
 {id:'cash',label:'Cash',initial:-300,formula:['add','prev.cash','revenue']},
 {id:'margin',label:'Margin',formula:['if',['gt','revenue',0],['div',100,'revenue'],0]}],
 metrics:[{output:'cash',aggregate:'last',label:'Closing cash'},{output:'revenue',aggregate:'sum',label:'Revenue'}],
 charts:[{title:'Cash',chart_type:'line',y_fields:['cash'],compare_baseline:true}]
};
test('business inputs drive recurring cash, totals and comparison without mutating baseline',()=>{
 const baseline=calculateScenario(model,{price:10})!;
 const changed=calculateScenario(model,{price:15})!;
 assert.deepEqual(baseline.rows.map(r=>r.cash),[-100,100,300]);
 assert.deepEqual(changed.rows.map(r=>r.cash),[0,300,600]);
 assert.equal(baseline.metrics[1].value,600);
 assert.equal(changed.metrics[1].value,900);
 assert.equal(model.inputs[0].value,10);
});
test('lazy guards allow zero activity while unguarded division is rejected',()=>{
 assert.equal(calculateScenario(model,{price:0})!.rows[0].margin,0);
 assert.throws(()=>evaluate(['div',1,0],{}));
 assert.equal(calculateScenario({...model,outputs:[{id:'bad',label:'Bad',formula:['div',1,0]}]}, {price:10}),null);
});
test('malformed arithmetic, nonfinite inputs and unbounded horizons cannot yield results',()=>{
 for(const expr of [['sub',1],['pow',10,1000],['exec','x'],['add',1],['div',1,2,3]])assert.throws(()=>evaluate(expr as never,{}));
 for(const price of [NaN,Infinity,-1,101])assert.equal(calculateScenario(model,{price}),null);
 for(const periods of [0,121,2.5])assert.equal(calculateScenario({...model,periods},{price:10}),null);
 assert.throws(()=>evaluate('constructor',{}));
});
test('discounted cash flow uses each period and upfront capital exactly once',()=>{
 const r=calculateScenario({...model,outputs:[{id:'pv',label:'NPV',initial:-300,formula:['add','prev.pv',['div',200,['pow',1.1,'period']]]}],metrics:[{output:'pv',aggregate:'last',label:'NPV'}]}, {price:10})!;
 assert.ok(Math.abs(r.metrics[0].value-197.3703981968)<1e-8);
});
