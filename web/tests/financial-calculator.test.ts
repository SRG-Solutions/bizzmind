import {test} from 'node:test';
import assert from 'node:assert/strict';
import {calculate} from '../src/lib/financial-calculator.ts';
const loan={price:100000,down:0,rate:4,years:30,extra:0};
test('fixed-rate payment matches CFPB example and settles principal',()=>{
 const r=calculate('mortgage',loan)!;
 assert.ok(Math.abs(r.metrics[0].value-477.415295)<0.00001);
 assert.equal(r.rows.at(-1)!.balance,0);
 assert.ok(Math.abs(r.metrics[2].value-r.metrics[1].value-100000)<1e-6);
});
test('zero interest, full down payment and overpayments remain finite',()=>{
 assert.equal(calculate('mortgage',{...loan,rate:0})!.metrics[0].value,100000/360);
 assert.equal(calculate('mortgage',{...loan,down:100000})!.metrics[3].value,0);
 const extra=calculate('mortgage',{...loan,extra:1000})!;
 assert.ok(extra.metrics[1].value<calculate('mortgage',loan)!.metrics[1].value);
 assert.ok(extra.metrics[3].value<360);
 assert.equal(extra.rows.at(-1)!.balance,0);
});
test('invalid inputs do not produce misleading results',()=>{
 for(const patch of [{price:NaN},{down:100001},{years:2.5},{rate:-1},{extra:Infinity}]) assert.equal(calculate('mortgage',{...loan,...patch}),null);
 assert.equal(calculate('forecast',{revenue:1,growth:201,margin:40,costs:0,years:2}),null);
});
test('forecast applies annual compound growth and fixed costs',()=>{
 const r=calculate('forecast',{revenue:100,growth:10,margin:50,costs:20,years:2})!;
 assert.ok(Math.abs(r.metrics[0].value-121)<1e-9);
 assert.ok(Math.abs(r.metrics[1].value-40.5)<1e-9);
 assert.ok(Math.abs(r.metrics[2].value-75.5)<1e-9);
});
test('investment uses effective annual return and month-end contributions',()=>{
 assert.ok(Math.abs(calculate('investment',{initial:1000,contribution:0,return:10,years:2})!.metrics[0].value-1210)<1e-8);
 assert.equal(calculate('investment',{initial:1000,contribution:100,return:0,years:1})!.metrics[0].value,2200);
 assert.ok(calculate('investment',{initial:1000,contribution:0,return:-10,years:1})!.metrics[2].value<0);
});
test('demand includes stock, timed receipts, buffer and shortage',()=>{
 const input={demand:300,growth:0,stock:50,incoming:100,lead:10,horizon:30,safety:5};
 const r=calculate('demand',input)!;
 assert.equal(r.metrics[0].value,300);
 assert.equal(r.metrics[1].value,200);
 assert.equal(r.metrics[2].value,150);
 assert.equal(r.rows[9].stock,-40);
 assert.equal(r.rows[10].stock,50);
 assert.equal(calculate('demand',{...input,lead:40})!.metrics[1].value,300);
 assert.equal(calculate('demand',{...input,growth:-100})!.metrics[1].value,0);
});

test('every chart output responds to the shared scenario assumptions',()=>{
 const input={revenue:100,growth:10,margin:50,costs:20,years:2};
 const before=calculate('forecast',input)!.rows[1];
 const after=calculate('forecast',{...input,growth:20})!.rows[1];
 assert.ok(after.revenue>before.revenue);
 assert.ok(after.profit>before.profit);
 assert.ok(Math.abs(after.revenue-after.expenses-after.profit)<1e-9);
 const investment=calculate('investment',{initial:1000,contribution:100,return:0,years:1})!.rows.at(-1)!;
 assert.equal(investment.value,investment.contributed);
 assert.equal(investment.gain,0);
});
