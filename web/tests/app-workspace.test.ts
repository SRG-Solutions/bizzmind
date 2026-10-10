import {test} from 'node:test';
import assert from 'node:assert/strict';
import {selectAppRows} from '../src/lib/app-workspace.ts';
test('search matches Cyrillic and keeps original rows unchanged',()=>{
 const rows=[{name:'София',value:12},{name:'Варна',value:2}];
 assert.deepEqual(selectAppRows(rows,'СОФ',null,'bg-BG'),[rows[0]]);
 assert.deepEqual(selectAppRows(rows,'',{column:'value',descending:false},'en-GB'),[rows[1],rows[0]]);
 assert.equal(rows[0].value,12);
});
test('numeric order and missing values work in both directions',()=>{
 const rows=[{value:2},{value:null},{value:100}];
 assert.deepEqual(selectAppRows(rows,'',{column:'value',descending:true},'en-GB').map(x=>x.value),[100,2,null]);
 assert.deepEqual(selectAppRows(rows,'',{column:'value',descending:false},'en-GB').map(x=>x.value),[2,100,null]);
 assert.deepEqual(selectAppRows(rows,'missing',null,'en-GB'),[]);
});
