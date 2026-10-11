import asyncio
import worker
from bizzmind.agent import CancelledByUser


def test_cancelled_job_does_not_kill_worker_or_finish_for_billing(monkeypatch):
    queue=iter([{'id':'qa-cancel','project_id':'qa','kind':'chat','payload':{}},None])
    cancelled=[];finished=[]
    async def cancel_job(job):raise CancelledByUser()
    monkeypatch.setattr(worker,'_stop',False)
    monkeypatch.setattr(worker.signal,'signal',lambda *a:None)
    monkeypatch.setattr(worker.jobs,'requeue_stale',lambda:0)
    monkeypatch.setattr(worker.jobs,'claim',lambda:next(queue))
    monkeypatch.setattr(worker.jobs,'cancel',lambda id:cancelled.append(id))
    monkeypatch.setattr(worker.jobs,'finish',lambda *args:finished.append(args))
    monkeypatch.setattr(worker,'run_job',cancel_job)
    asyncio.run(worker.main(once=True))
    assert cancelled==['qa-cancel']
    assert finished==[]
