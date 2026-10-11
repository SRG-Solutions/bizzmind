/** Deterministic scenario models. No generated code, data writes or network calls. */
export type CalculatorKind = 'mortgage' | 'forecast' | 'investment' | 'demand';
export type CalculatorInputs = Record<string, number>;
export interface CalculatorConfig {
  kind: CalculatorKind;
  defaults: CalculatorInputs;
  charts?: CalculatorChart[];
  currency?: 'EUR' | 'USD' | 'GBP' | 'BGN';
}
export interface CalculatorChart {
  title?: string;
  chart_type: 'line' | 'area' | 'bar';
  y_fields: string[];
  compare_baseline?: boolean;
}
export const calculatorSeries: Record<CalculatorKind, string[]> = {
  mortgage: ['balance','principal_paid','interest_paid'],
  forecast: ['revenue','profit','expenses'],
  investment: ['value','contributed','gain'],
  demand: ['stock','shortage','demand','receipts'],
};
export const defaultCalculatorCharts: Record<CalculatorKind, CalculatorChart[]> = {
  mortgage: [{chart_type:'area',y_fields:['balance'],compare_baseline:true},{chart_type:'bar',y_fields:['principal_paid','interest_paid']}],
  forecast: [{chart_type:'line',y_fields:['revenue','expenses']},{chart_type:'area',y_fields:['profit'],compare_baseline:true}],
  investment: [{chart_type:'area',y_fields:['value','contributed']},{chart_type:'line',y_fields:['gain'],compare_baseline:true}],
  demand: [{chart_type:'line',y_fields:['stock'],compare_baseline:true},{chart_type:'area',y_fields:['shortage']},{chart_type:'bar',y_fields:['demand','receipts']}],
};
export interface CalculatorField { key: string; min: number; max: number; step: number }
export const calculatorFields: Record<CalculatorKind, CalculatorField[]> = {
  mortgage: [
    {key:'price',min:0,max:1e9,step:1000}, {key:'down',min:0,max:1e9,step:1000},
    {key:'rate',min:0,max:30,step:0.1}, {key:'years',min:1,max:40,step:1}, {key:'extra',min:0,max:1e7,step:50},
  ],
  forecast: [
    {key:'revenue',min:0,max:1e12,step:10000}, {key:'growth',min:-100,max:200,step:1},
    {key:'margin',min:0,max:100,step:1}, {key:'costs',min:0,max:1e12,step:10000}, {key:'years',min:1,max:10,step:1},
  ],
  investment: [
    {key:'initial',min:0,max:1e9,step:1000}, {key:'contribution',min:0,max:1e7,step:100},
    {key:'return',min:-50,max:100,step:0.1}, {key:'years',min:1,max:40,step:1},
  ],
  demand: [
    {key:'demand',min:0,max:1e9,step:10}, {key:'growth',min:-100,max:200,step:1},
    {key:'stock',min:0,max:1e9,step:10}, {key:'incoming',min:0,max:1e9,step:10},
    {key:'lead',min:0,max:365,step:1}, {key:'horizon',min:1,max:365,step:1}, {key:'safety',min:0,max:365,step:1},
  ],
};
export interface CalculatorResult {
  metrics: {key:string;value:number;unit:'money'|'units'|'months'}[];
  rows: {period:number;[series:string]:number}[];
  chartKey: string;
  periodKey: string;
}
export function validInputs(kind:CalculatorKind, input:CalculatorInputs) {
  return calculatorFields[kind]?.every(f=>Number.isFinite(input[f.key])&&input[f.key]>=f.min&&input[f.key]<=f.max&&(!['years','lead','horizon','safety'].includes(f.key)||Number.isInteger(input[f.key]))) && (kind!=='mortgage'||input.down<=input.price);
}
export function calculate(kind:CalculatorKind, input:CalculatorInputs):CalculatorResult|null {
  if(!validInputs(kind,input))return null;
  if(kind==='mortgage') {
    const principal=input.price-input.down, n=input.years*12, r=input.rate/1200;
    const payment=principal===0?0:r===0?principal/n:principal*r/(-Math.expm1(-n*Math.log1p(r)));
    let balance=principal, interest=0, months=0;
    const rows=[{period:0,balance:principal,principal_paid:0,interest_paid:0}];
    for(let m=1;m<=n;m++) {
      if(balance>1e-7) {
        const charge=balance*r;
        const paid=Math.min(balance+charge,payment+input.extra);
        balance=Math.max(0,balance+charge-paid); interest+=charge; months=m;
      } else balance=0;
      if(m%12===0)rows.push({period:m/12,balance:balance<1e-7?0:balance,principal_paid:principal-balance,interest_paid:interest});
    }
    return {metrics:[{key:'payment',value:payment,unit:'money'},{key:'interest',value:interest,unit:'money'},{key:'total',value:principal+interest,unit:'money'},{key:'payoff',value:months,unit:'months'}],rows,chartKey:'balance',periodKey:'year'};
  }
  if(kind==='forecast') {
    const rows=Array.from({length:input.years},(_,i)=>{const revenue=input.revenue*Math.pow(1+input.growth/100,i+1);const expenses=revenue*(1-input.margin/100)+input.costs;return {period:i+1,revenue,expenses,profit:revenue-expenses};});
    return {metrics:[{key:'revenue_result',value:input.revenue*Math.pow(1+input.growth/100,input.years),unit:'money'},{key:'profit',value:rows.at(-1)!.profit,unit:'money'},{key:'cumulative',value:rows.reduce((s,r)=>s+r.profit,0),unit:'money'}],rows,chartKey:'profit_path',periodKey:'year'};
  }
  if(kind==='investment') {
    // Annual effective return converted to a monthly rate; contributions at month end.
    const r=Math.expm1(Math.log1p(input.return/100)/12);
    let balance=input.initial;
    const rows=[{period:0,value:balance,contributed:input.initial,gain:0}];
    for(let m=1;m<=input.years*12;m++) {balance=balance*(1+r)+input.contribution;if(m%12===0)rows.push({period:m/12,value:balance,contributed:input.initial+input.contribution*m,gain:balance-input.initial-input.contribution*m});}
    const invested=input.initial+input.contribution*input.years*12;
    return {metrics:[{key:'future_value',value:balance,unit:'money'},{key:'invested',value:invested,unit:'money'},{key:'gain',value:balance-invested,unit:'money'}],rows,chartKey:'investment_path',periodKey:'year'};
  }
  // Demand is units per 30-day month; growth is a one-off planning adjustment.
  const daily=input.demand*(1+input.growth/100)/30;
  const target=daily*(input.horizon+input.safety);
  const order=Math.max(0,Math.ceil(target-input.stock-(input.lead<=input.horizon?input.incoming:0)));
  const rows=Array.from({length:input.horizon+1},(_,day)=>{const receipts=day>=input.lead?input.incoming:0;const stock=input.stock-daily*day+receipts;return {period:day,stock,shortage:Math.max(0,-stock),demand:daily*day,receipts};});
  const shortage=Math.max(0,-Math.min(...rows.map(r=>r.stock)));
  return {metrics:[{key:'planned_demand',value:daily*input.horizon,unit:'units'},{key:'order',value:order,unit:'units'},{key:'shortage',value:shortage,unit:'units'}],rows,chartKey:'stock_path',periodKey:'day'};
}
