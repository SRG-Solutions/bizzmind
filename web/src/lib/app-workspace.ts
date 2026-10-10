/** Filter and sort only loaded records; preserve the server's original array. */
export function selectAppRows<T extends Record<string, unknown>>(rows: T[], search: string, sort: {column: string; descending: boolean} | null, locale: string): T[] {
  const query=search.trim().toLocaleLowerCase(locale);
  const result=rows.filter(row=>!query||Object.values(row).some(v=>String(v??'').toLocaleLowerCase(locale).includes(query)));
  if(!sort)return result;
  return result.sort((a,b)=>{
    const x=a[sort.column],y=b[sort.column];
    if(x==null)return y==null?0:1;
    if(y==null)return -1;
    const comparison=typeof x==='number'&&typeof y==='number'?x-y:String(x).localeCompare(String(y),locale,{numeric:true});
    return sort.descending?-comparison:comparison;
  });
}
