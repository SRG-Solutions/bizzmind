/** Small arithmetic language for generated apps. Never evaluates JavaScript or SQL. */
export type Expression = number | string | [string, ...Expression[]];
export interface ScenarioInput { id:string; label:string; unit?:string; value:number; min:number; max:number; step:number }
export interface ScenarioOutput { id:string; label:string; unit?:string; formula:Expression; initial?:Expression }
export interface ScenarioSpec {
  inputs:ScenarioInput[];
  periods:Expression;
  period_label:string;
  outputs:ScenarioOutput[];
  metrics:{output:string;aggregate:'last'|'sum'|'min'|'max';label:string}[];
  charts:{title:string;chart_type:'line'|'area'|'bar';y_fields:string[];compare_baseline?:boolean}[];
  presets?:{name:string;values:Record<string,number>}[];
}
export function evaluate(expr:Expression, values:Record<string,number>, depth=0):number {
  if(depth>12)throw Error('depth');
  if(typeof expr==='number'){if(!Number.isFinite(expr))throw Error('number');return expr;}
  if(typeof expr==='string'){if(!Object.hasOwn(values,expr)||!Number.isFinite(values[expr]))throw Error('reference');return values[expr];}
  if(!Array.isArray(expr))throw Error('expression');
  const [op,...args]=expr;
  const arities:Record<string,number>={sub:2,div:2,pow:2,abs:1,if:3,gt:2,gte:2,lt:2,lte:2};
  if(['add','mul','min','max'].includes(op)){if(args.length<2||args.length>16)throw Error('arity');}
  else if(!Object.hasOwn(arities,op)||args.length!==arities[op])throw Error('arity');
  if(op==='if') {if(args.length!==3)throw Error('arity');return evaluate(args[evaluate(args[0],values,depth+1)?1:2],values,depth+1);}
  const a=args.map(e=>evaluate(e,values,depth+1));
  let result:number;
  switch(op){
    case 'add':result=a.reduce((s,v)=>s+v,0);break;
    case 'mul':result=a.reduce((s,v)=>s*v,1);break;
    case 'sub':result=a[0]-a[1];break;
    case 'div':if(a[1]===0)throw Error('zero');result=a[0]/a[1];break;
    case 'pow':result=Math.pow(a[0],a[1]);break;
    case 'min':result=Math.min(...a);break;
    case 'max':result=Math.max(...a);break;
    case 'abs':result=Math.abs(a[0]);break;
    case 'gt':result=Number(a[0]>a[1]);break;
    case 'gte':result=Number(a[0]>=a[1]);break;
    case 'lt':result=Number(a[0]<a[1]);break;
    case 'lte':result=Number(a[0]<=a[1]);break;
    default:throw Error('operator');
  }
  if(!Number.isFinite(result)||Math.abs(result)>1e100)throw Error('overflow');
  return result;
}
export function calculateScenario(spec:ScenarioSpec, values:Record<string,number>) {
  try {
    if(spec.inputs.some(f=>!Number.isFinite(values[f.id])||values[f.id]<f.min||values[f.id]>f.max))return null;
    const count=evaluate(spec.periods,values);
    if(!Number.isInteger(count)||count<1||count>120)return null;
    let previous:Record<string,number>=Object.fromEntries(spec.outputs.map(o=>[o.id,o.initial===undefined?0:evaluate(o.initial,values)]));
    const rows:Record<string,number>[]=[];
    for(let period=1;period<=count;period++){
      const context:Record<string,number>={...values,period,...Object.fromEntries(Object.entries(previous).map(([key,value])=>[`prev.${key}`,value]))};
      const row:Record<string,number>={period};
      for(const output of spec.outputs){row[output.id]=evaluate(output.formula,context);context[output.id]=row[output.id];}
      rows.push(row);previous=row;
    }
    const metrics=spec.metrics.map(m=>{
      const series=rows.map(r=>r[m.output]);
      const value=m.aggregate==='sum'?series.reduce((s,v)=>s+v,0):m.aggregate==='min'?Math.min(...series):m.aggregate==='max'?Math.max(...series):series.at(-1)!;
      return {...m,value,unit:spec.outputs.find(o=>o.id===m.output)?.unit??''};
    });
    return {rows,metrics};
  }catch{return null;}
}
