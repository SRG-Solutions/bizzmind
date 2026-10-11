/** Watching a job is independent of the panel/browser tab displaying its progress. */
export class JobCancelled extends Error {}
export interface WatchedJob<T, E> {
  status: 'queued' | 'running' | 'done' | 'failed' | 'cancelled';
  result?: T | null;
  error?: string | null;
  events: E[];
}
export async function pollJob<T, E extends {seq:number}>({read,wait,cancel,onEvent,signal}: {
  read:(since:number)=>Promise<WatchedJob<T,E>>;
  wait:(ms:number)=>Promise<void>;
  cancel:()=>Promise<unknown>;
  onEvent?:(event:E)=>void;
  signal?:AbortSignal;
}):Promise<T> {
  let since=0, failures=0;
  for (;;) {
    await wait(Math.min(10_000,1200*Math.max(1,failures)));
    // Only an explicit Stop signal cancels server work. Transient disconnections
    // and background-tab timer throttling must not be mistaken for cancellation.
    if(signal?.aborted){await cancel();throw new JobCancelled('cancelled');}
    let job:WatchedJob<T,E>;
    try {job=await read(since);failures=0;}
    catch(error){
      const status=(error as {status?:number})?.status;
      if(error instanceof TypeError || (typeof status==='number'&&(status>=500||status===408||status===429))){failures++;continue;}
      throw error;
    }
    for(const event of job.events){if(event.seq>since){since=event.seq;onEvent?.(event);}}
    if(job.status==='done')return (job.result??{}) as T;
    if(job.status==='cancelled')throw new JobCancelled('cancelled');
    if(job.status==='failed')throw new Error(job.error??'job failed');
  }
}
