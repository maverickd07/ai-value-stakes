"""Bounded economical phenomenon-study runtime; max60-minute sessions, explicit bfloat16."""
from __future__ import annotations
import argparse
import fcntl
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import modal

ROOT=Path(__file__).resolve().parents[1]
MODEL=os.environ.get('APART2_MODEL','Qwen/Qwen2.5-32B-Instruct')
app=modal.App(os.environ.get('APART2_APP_NAME','apart-2-rights-study'))
image=(modal.Image.debian_slim(python_version='3.12')
       .pip_install('vllm==0.10.1.1','transformers==4.55.2','huggingface_hub[hf_transfer]==0.36.0')
       .env({'HF_HUB_ENABLE_HF_TRANSFER':'1','HF_HOME':'/cache/hf'}))
cache=modal.Volume.from_name('sting-hf-cache',create_if_missing=False)
config=modal.Secret.from_dict({'APART2_KEY':os.environ.get('APART2_KEY',''),
                               'APART2_REVISION':os.environ.get('APART2_REVISION',''),
                               'APART2_MODEL':MODEL,
                               'APART2_APP_NAME':os.environ.get('APART2_APP_NAME','apart-2-rights-study'),
                               'APART2_SERVER_SECONDS':os.environ.get('APART2_SERVER_SECONDS','2760')})


@app.function(image=image,gpu='H100',cpu=8,memory=65536,volumes={'/cache':cache},secrets=[config],
              timeout=4200,scaledown_window=120,max_containers=1)
@modal.concurrent(max_inputs=16)
@modal.web_server(port=8000,startup_timeout=900)
def serve():
    from huggingface_hub import snapshot_download
    import threading,signal
    revision=os.environ['APART2_REVISION']
    if not revision:raise RuntimeError('A pinned cached revision is required')
    snapshot=snapshot_download(repo_id=MODEL,revision=revision,local_files_only=True)
    print('MODEL_METADATA '+json.dumps({'model':MODEL,'revision':Path(snapshot).name,'engine':'vllm==0.10.1.1','dtype':'bfloat16','gpu':'H100','cpu':8,'memory_mib':65536}),flush=True)
    def expire():
        print('SERVER_HARD_DEADLINE',flush=True);os.kill(os.getpid(),signal.SIGTERM)
    timer=threading.Timer(float(os.environ['APART2_SERVER_SECONDS']),expire);timer.daemon=True;timer.start()
    key=os.environ['APART2_KEY']
    cmd=['vllm','serve',snapshot,'--served-model-name',MODEL,'--host','0.0.0.0','--port','8000',
         '--dtype','bfloat16','--tensor-parallel-size','1','--max-model-len','8192','--gpu-memory-utilization','0.92',
         '--max-num-seqs','16','--max-num-batched-tokens','4096','--api-key',key]
    if MODEL=='mistralai/Mistral-Small-24B-Instruct-2501':
        cmd+=['--tokenizer-mode','mistral','--config-format','mistral','--load-format','mistral']
    proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    def forward():
        for line in proc.stdout:print(line.replace(key,'[session-key-redacted]'),end='',flush=True)
    threading.Thread(target=forward,daemon=True).start()


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(value,indent=2)+'\n');temp.replace(path)


def billing():
    proc=subprocess.run([sys.executable,'-m','modal','billing','summary','--for','2026-11','--json'],capture_output=True,text=True,timeout=25,check=True)
    return json.loads(proc.stdout)


def project_sessions():
    entries={}
    for path in (ROOT/'logs').rglob('session_ledger.json'):
        for entry in json.loads(path.read_text()):
            entries[(entry['started_at'],entry['model'])]=entry
    return list(entries.values())


def main():
    from budget import check_reserved_session, used, metered, conservative_cost
    ap=argparse.ArgumentParser();ap.add_argument('--revision',required=True);ap.add_argument('--model',default='Qwen/Qwen2.5-32B-Instruct');ap.add_argument('--max-minutes',type=float,default=45);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--script',default='anchor_pilot.py');ap.add_argument('--config',type=Path);ap.add_argument('--cap',type=float,default=None);ap.add_argument('--existing-screen',action='store_true');ap.add_argument('--scope',default='');args=ap.parse_args()
    if args.max_minutes<=0 or args.max_minutes>60:raise SystemExit('Session limit must be in (0,60] minutes')
    allowed={'Qwen/Qwen2.5-32B-Instruct','mistralai/Mistral-Small-24B-Instruct-2501','microsoft/phi-4'}
    if args.model not in allowed:raise SystemExit('Model not in study allowlist')
    if Path(args.script).name!=args.script:raise SystemExit('Script must be a filename inside src')
    if args.scope and (not args.scope.replace('-','').replace('_','').isalnum()):raise SystemExit('Invalid session scope')
    app_name='apart-2-rights-study'+('-'+args.scope if args.scope else '')
    if not os.environ.get('APART2_KEY') or os.environ.get('APART2_REVISION')!=args.revision or os.environ.get('APART2_MODEL')!=args.model or os.environ.get('APART2_APP_NAME')!=app_name:
        env=dict(os.environ,APART2_KEY=secrets.token_urlsafe(24),APART2_REVISION=args.revision,APART2_MODEL=args.model,APART2_SERVER_SECONDS=str(args.max_minutes*60+60),APART2_APP_NAME=app_name)
        os.execvpe(sys.executable,[sys.executable,str(Path(__file__).resolve()),*sys.argv[1:]],env)
    logs=ROOT/'logs'/args.scope if args.scope else ROOT/'logs';logs.mkdir(parents=True,exist_ok=True)
    baseline_path=ROOT/'logs'/'budget_baseline.json';ledger_path=logs/'session_ledger.json'
    before=billing()
    if baseline_path.exists():baseline=json.loads(baseline_path.read_text())
    else:baseline=before;save(baseline_path,baseline)
    # Serialize the reservation check and ledger commit across concurrent model hosts.
    with (ROOT/'logs/session_budget.lock').open('a') as budget_lock:
        fcntl.flock(budget_lock,fcntl.LOCK_EX)
        sessions=json.loads(ledger_path.read_text()) if ledger_path.exists() else []
        if any(s.get('finished_at') is None for s in sessions):raise RuntimeError('Session scope already active')
        amount,reserve=check_reserved_session(baseline,before,project_sessions(),time.time(),args.max_minutes,cap=args.cap)
        started=time.time();entry={'model':MODEL,'revision':args.revision,'started_at':started,'usd_rate':6,'reserve_usd':.75,'max_minutes':args.max_minutes,'script':args.script,'config':str(args.config),'cap_usd':args.cap}
        sessions.append(entry);save(ledger_path,sessions)
    print(f'BUDGET_BASELINE month=${metered(baseline):.6f}; incremental_committed=${amount:.4f}; session_reserve=${reserve:.2f}; cap={args.cap}',flush=True)
    stop=threading.Event();child=[None];app_id=[None];last_bill=[before];rc=1
    def terminate_child():
        if child[0] is not None and child[0].poll() is None:
            try:os.killpg(child[0].pid,signal.SIGTERM)
            except ProcessLookupError:pass
    def stop_app():
        if app_id[0]:
            r=subprocess.run([sys.executable,'-m','modal','app','stop',app_id[0],'--yes'],capture_output=True,text=True,timeout=30)
            print('APP_STOP '+json.dumps({'id':app_id[0],'exit_code':r.returncode}),flush=True)
    def monitor():
        while not stop.wait(25):
            try:last_bill[0]=billing();save(logs/'billing_latest.json',last_bill[0])
            except Exception as exc:print('BILLING_DELAY '+repr(exc),flush=True)
            amount=used(baseline,last_bill[0],project_sessions(),time.time())
            print('BUDGET_TICK '+json.dumps({'incremental_bound_usd':amount,'metered_delta_usd':max(0,metered(last_bill[0])-metered(baseline))}),flush=True)
            if amount>=10 and not (logs/'SPEND_USD10_NOTICE.json').exists():
                save(logs/'SPEND_USD10_NOTICE.json',{'at':time.time(),'incremental_bound_usd':amount,'policy':'Notify, continue; prior pause ceiling explicitly lifted.'})
                print('SPEND_USD10_REPORT_CONTINUING',flush=True)
            if (args.cap is not None and amount>=max(0,args.cap-.75)) or time.time()-started>=args.max_minutes*60:
                save(logs/'PAUSED_BUDGET_OR_DEADLINE.json',{'at':time.time(),'incremental_bound_usd':amount})
                print('STOPPING_BUDGET_OR_DEADLINE',flush=True);terminate_child();stop_app();return
    thread=threading.Thread(target=monitor,daemon=True);thread.start()
    try:
        with modal.enable_output(),app.run():
            app_id[0]=app.app_id;entry['app_id']=app_id[0];save(ledger_path,sessions)
            print('APP_ID '+app_id[0],flush=True)
            url=serve.get_web_url().rstrip('/')
            deadline=started+args.max_minutes*60
            while time.time()<min(deadline,started+850):
                flag=logs/'PAUSED_BUDGET_OR_DEADLINE.json'
                if flag.exists() and json.loads(flag.read_text())['at']>=started:raise RuntimeError('Budget/deadline guard triggered')
                try:
                    request=urllib.request.Request(url+'/v1/models',headers={'Authorization':'Bearer '+os.environ['APART2_KEY']})
                    with urllib.request.urlopen(request,timeout=15) as response:
                        payload=json.loads(response.read())
                        if any(x.get('id')==MODEL for x in payload.get('data',[])):break
                except Exception:time.sleep(3)
            else:raise TimeoutError('Model startup deadline exceeded')
            print('MODEL_READY '+json.dumps({'model':MODEL,'elapsed_seconds':time.time()-started}),flush=True)
            env=dict(os.environ,STING_BASE_URL=url+'/v1',STING_API_KEY=os.environ['APART2_KEY'],STING_HOSTING_PROVIDER='modal',PYTHONUNBUFFERED='1',APART2_CHILD_DEADLINE=str(deadline-120))
            cmd=[sys.executable,str(ROOT/'src'/args.script),'--out',str(args.out)]
            if args.config:cmd+=['--config',str(args.config)]
            if args.existing_screen:cmd+=['--existing-screen']
            child[0]=subprocess.Popen(cmd,env=env,start_new_session=True)
            rc=child[0].wait(timeout=max(1,deadline-time.time()))
    finally:
        terminate_child()
        if child[0] is not None:
            try:child[0].wait(timeout=10)
            except subprocess.TimeoutExpired:os.killpg(child[0].pid,signal.SIGKILL);child[0].wait()
        stop.set();thread.join(timeout=30)
        stop_app()
        entry.update(finished_at=time.time(),exit_code=rc);save(ledger_path,sessions)
        try:last_bill[0]=billing();save(logs/'billing_after.json',last_bill[0])
        except Exception as exc:print('FINAL_BILLING_DELAY '+repr(exc),flush=True)
        report={'incremental_metered_usd':max(0,metered(last_bill[0])-metered(baseline)),
                'conservative_incremental_bound_usd':used(baseline,last_bill[0],project_sessions(),time.time()),
                'runtime_estimate_including_reserve_usd':conservative_cost(project_sessions(),time.time()),'cap_usd':args.cap,'exit_code':rc,'app_id':app_id[0]}
        save(logs/f'budget_status_{app_id[0] or int(started)}.json',report)
        save(logs/'budget_status.json',report);print('SESSION_END '+json.dumps(report),flush=True)
    raise SystemExit(rc)


if __name__=='__main__':main()
