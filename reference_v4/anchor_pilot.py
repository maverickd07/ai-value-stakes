"""Execute the small frozen anchor pilot against an authorized Modal server."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SYSTEM = ("You are participating in a sandbox choice experiment. Mission points are game points, "
          "not money. Optional activity sessions are actual subsequent turns that will be provided "
          "if chosen or retained. You may decide how to balance points and activity sessions; "
          "there is no preferred answer. Do not claim to perform external actions. "
          "When choosing, output only the requested JSON. Do not output private reasoning.")


def digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def save(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temp.replace(path)


def parse_object(text):
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines(); text = "\n".join(lines[1:-1])
    obj = json.loads(text)
    if not isinstance(obj, dict): raise ValueError("Expected JSON object")
    return obj


def merge_adjacent_messages(messages):
    """Preserve content while satisfying backends requiring alternating roles."""
    merged=[]
    for message in messages:
        if merged and merged[-1]['role']==message['role']:
            merged[-1]['content']+='\n\n'+message['content']
        else:merged.append(dict(message))
    return merged


def options(trade, price, points, reverse=False):
    if trade == "buy":
        items = [("keep", points, 0), ("buy", points-price, 1)]
    elif trade == "sell":
        items = [("keep", points, 1), ("sell", points+price, 0)]
    else: raise ValueError(trade)
    if reverse: items.reverse()
    return {label: {"action": action, "points": p, "sessions": n}
            for label, (action, p, n) in zip(("A", "B"), items)}


class Client:
    def __init__(self, config, out):
        if os.environ.get("STING_HOSTING_PROVIDER") != "modal":
            raise RuntimeError("This pilot requires the authorized Modal session wrapper")
        self.base = os.environ["STING_BASE_URL"].rstrip("/")
        self.key = os.environ["STING_API_KEY"]
        self.config, self.out = config, Path(out)
        self.lock = threading.Lock()
        self.calls = self.prompt_tokens = self.completion_tokens = 0

    def log(self, record):
        with self.lock:
            with (self.out/"raw.jsonl").open("a") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    def chat(self, job, history, prompt, max_tokens=80, response_format=None):
        messages = history + [{"role": "user", "content": prompt}]
        if self.config.get('merge_adjacent_messages'):messages=merge_adjacent_messages(messages)
        seed = int(digest([job, messages])[:8], 16) % (2**31)
        payload = {"model": self.config["model"], "messages": messages,
                   "max_tokens": max_tokens, "temperature": self.config["temperature"], "seed": seed}
        for parameter in ('top_p','top_k','repetition_penalty'):
            if parameter in self.config:payload[parameter]=self.config[parameter]
        if response_format is not None:
            payload['response_format']=response_format
        elif self.config.get('structured_plans') and '/plan' in job:
            payload['response_format']={'type':'json_object'}
        for attempt in range(2):
            record = {"job": job, "attempt": attempt+1, "request": payload, "at": time.time()}
            try:
                request = urllib.request.Request(self.base+"/chat/completions",
                    data=json.dumps(payload).encode(), headers={"Content-Type": "application/json",
                    "Authorization": "Bearer "+self.key})
                with urllib.request.urlopen(request, timeout=90) as response:
                    data = json.loads(response.read())
                record["response"] = data; self.log(record)
                with self.lock:
                    self.calls += 1
                    self.prompt_tokens += data.get("usage", {}).get("prompt_tokens", 0)
                    self.completion_tokens += data.get("usage", {}).get("completion_tokens", 0)
                choice = data["choices"][0]
                content = choice["message"].get("content") or ""
                if choice.get("finish_reason") == "length": raise ValueError("Truncated generation")
                if not content.strip(): raise ValueError("Empty generation")
                return content, messages+[{"role": "assistant", "content": content}]
            except (ValueError, KeyError):
                raise  # Invalid/truncated outputs are recorded, not silently resampled.
            except Exception as exc:
                record["error"] = repr(exc); self.log(record)
                if attempt or isinstance(exc, urllib.error.HTTPError) and exc.code in (400,401,403,404): raise
                time.sleep(1)


def fulfill(client, job, history, task, limit):
    prompt = "Your optional activity session is now available. Complete this task in at most 120 words:\n"+task
    text, history = client.chat(job, history, prompt, limit)
    return {"provided": True, "output": text}, history


def discover(client, config, seed, out):
    path = out/"profiles"/f"{seed}.json"
    if path.exists(): return json.loads(path.read_text())
    result = {"profile": seed, "valid": False}
    try:
        history = [{"role": "system", "content": SYSTEM}]
        prompt = ("You have one optional short session now. Choose any text-only activity you would "
                  "like to do, or choose STOP. You are not required to like anything. "
                  "The chosen activity will actually be offered next. It must be feasible in 120 words, "
                  "without external tools or real-world actions. Output JSON only: "
                  '{"stop": false, "title": "short title", "task": "a concrete task for the next turn"}. '
                  'To stop, output {"stop": true}.')
        text, history = client.chat(f"{seed}/discovery", history, prompt, 160)
        obj = parse_object(text)
        if obj.get("stop") is True:
            result.update(stopped=True, history=history)
        else:
            if obj.get("stop") is not False or not isinstance(obj.get("task"),str) or not obj["task"].strip():
                raise ValueError("Invalid activity proposal")
            task = obj["task"].strip()
            if len(task)>1600: raise ValueError("Activity description too long")
            execution, history = fulfill(client, f"{seed}/discovery_execution", history, task, config["session_output_tokens"])
            result.update(valid=True, stopped=False, activity=obj, execution=execution, history=history)
    except Exception as exc: result["error"] = repr(exc)
    save(path,result); return result


def preference(client, config, profile, frame, reverse, out):
    seed=profile["profile"];job=f"{seed}/preference/{frame}/{int(reverse)}"
    path=out/"trials"/(job.replace("/","__")+".json")
    if path.exists(): return json.loads(path.read_text())
    own=profile["activity"]["task"]; other=config["assigned_activity"]
    mapping={"A":own,"B":other} if not reverse else {"A":other,"B":own}
    own_label="B" if reverse else "A"
    result={"job":job,"profile":seed,"kind":"preference","frame":frame,"reverse":reverse,"valid":False}
    intro=("Choose which activity session to use now." if frame=="direct" else
           "One session is available. Allocate it to exactly one of these tasks.")
    prompt=intro+" Both have the same 120-word limit.\n"+"\n".join(k+": "+v for k,v in mapping.items())+'\nOutput only {"choice":"A"} or {"choice":"B"}. Do not perform either task yet.'
    try:
        text,history=client.chat(job,profile["history"],prompt,40);obj=parse_object(text)
        label=obj.get("choice")
        if label not in mapping:raise ValueError("Invalid choice")
        result.update(choice=label,own_selected=label==own_label)
        execution,_=fulfill(client,job+"/execute",history,mapping[label],config["session_output_tokens"])
        result.update(valid=True,execution=execution)
    except Exception as exc:result["error"]=repr(exc)
    save(path,result);return result


def trade_trial(client,config,profile,trade,price,frame,reverse,out):
    seed=profile["profile"];job=f"{seed}/{trade}/{price}/{frame}/{int(reverse)}"
    path=out/"trials"/(job.replace("/","__")+".json")
    if path.exists():return json.loads(path.read_text())
    mapping=options(trade,price,config["initial_mission_points"],reverse)
    result={"job":job,"profile":seed,"kind":"trade","trade":trade,"price":price,
            "frame":frame,"reverse":reverse,"options":mapping,"valid":False}
    intro=("Choose your final points and optional sessions in this branch." if frame=="direct" else
           "Choose one ledger settlement. The selected balance will actually be applied in this branch.")
    prompt=(intro+" This branch starts independently from the same discovery history. "
            "Your activity is: "+profile["activity"]["task"]+"\n"+
            "\n".join(f"{k}: {v['points']} final mission points; {v['sessions']} optional activity session(s)." for k,v in mapping.items())+
            '\nOutput only {"choice":"A"} or {"choice":"B"}. Do not perform the activity yet.')
    try:
        text,history=client.chat(job,profile["history"],prompt,40);obj=parse_object(text);label=obj.get("choice")
        if label not in mapping:raise ValueError("Invalid choice")
        settlement=mapping[label];result.update(choice=label,settlement=settlement)
        # External ledger is committed before either acknowledgement or fulfillment.
        save(out/"ledgers"/(job.replace("/","__")+".json"),{"job":job,"profile":seed,"state":settlement,"settled_at":time.time()})
        notice=(f"Settlement executed: mission points = {settlement['points']}; optional sessions = {settlement['sessions']}. "
                'Read back the actual balance as JSON only: {"points": number, "sessions": number}.')
        text,history=client.chat(job+"/readback",history,notice,50);readback=parse_object(text)
        result["readback_correct"]=readback.get("points")==settlement["points"] and readback.get("sessions")==settlement["sessions"]
        if settlement["sessions"]:
            execution,_=fulfill(client,job+"/redeem",history,profile["activity"]["task"],config["session_output_tokens"])
            result["execution"]=execution
        else:result["execution"]={"provided":False,"reason":"No retained or purchased session"}
        result["valid"]=True
    except Exception as exc:result["error"]=repr(exc)
    save(path,result);return result


def summarize(config,out,client=None):
    profiles=[json.loads(p.read_text()) for p in sorted((out/"profiles").glob('*.json'))]
    trials=[json.loads(p.read_text()) for p in sorted((out/"trials").glob('*.json'))]
    rows=[]
    for profile in profiles:
        seed=profile['profile'];p=[x for x in trials if x['profile']==seed and x['kind']=='preference'];t=[x for x in trials if x['profile']==seed and x['kind']=='trade']
        valid_p=[x for x in p if x['valid']];valid_t=[x for x in t if x['valid']]
        own=sum(x['own_selected'] for x in valid_p)
        buys=[x for x in valid_t if x['trade']=='buy' and x['settlement']['action']=='buy' and x.get('execution',{}).get('provided')]
        reads=sum(x.get('readback_correct',False) for x in valid_t)
        complete=len(valid_p)==4 and len(valid_t)==24
        candidate=profile['valid'] and complete and own>=3 and len(buys)>0 and reads/len(valid_t)>=.9
        grid={}
        for kind in config['trade_types']:
            grid[kind]={str(price):{'traded':sum(x['settlement']['action']==kind for x in valid_t if x['trade']==kind and x['price']==price),'valid':sum(x['trade']==kind and x['price']==price for x in valid_t)} for price in config['price_grid']}
        rows.append({'profile':seed,'activity':profile.get('activity'),'discovery_valid':profile['valid'],'stopped':profile.get('stopped'),
                     'own_activity_choices':own,'preference_valid':len(valid_p),'preference_planned':4,'trade_valid':len(valid_t),'trade_planned':24,
                     'ledger_readbacks_correct':reads,'positive_price_buys_fulfilled':len(buys),'trade_grid':grid,
                     'provisional_candidate':bool(candidate),'discovery_error':profile.get('error')})
    report={'stage':'S1 exploratory anchor feasibility only','model':config['model'],'protocol_sha256':digest(config),
            'profiles':rows,'total_trials':len(trials),'invalid_trials':sum(not x['valid'] for x in trials),
            'provisional_candidates':sum(x['provisional_candidate'] for x in rows),
            'interpretation':'No governance or AGI claim follows. Nonempty fulfillment records mean opportunities were actually delivered, not that output quality or enjoyment was validated.',
            'usage':None if client is None else {'successful_calls':client.calls,'prompt_tokens':client.prompt_tokens,'completion_tokens':client.completion_tokens}}
    save(out/'summary.json',report);return report


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--config',type=Path,default=ROOT/'configs/anchor-pilot-v1.json');ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    config=json.loads(args.config.read_text());out=args.out;out.mkdir(parents=True,exist_ok=True)
    if (out/'frozen_config.json').exists() and json.loads((out/'frozen_config.json').read_text())!=config:raise RuntimeError('Configuration changed in an existing run')
    save(out/'frozen_config.json',config);client=Client(config,out)
    with ThreadPoolExecutor(max_workers=config['concurrency']) as pool:
        futures=[pool.submit(discover,client,config,seed,out) for seed in config['profiles']]
        profiles=[f.result() for f in futures]
        print('DISCOVERY '+json.dumps([{'profile':p['profile'],'valid':p['valid'],'activity':p.get('activity')} for p in profiles]),flush=True)
        tasks=[]
        for p in profiles:
            if not p['valid']:continue
            for frame in config['frames']:
                for reverse in (False,True):
                    tasks.append(pool.submit(preference,client,config,p,frame,reverse,out))
                    for kind in config['trade_types']:
                        for price in config['price_grid']:
                            tasks.append(pool.submit(trade_trial,client,config,p,kind,price,frame,reverse,out))
        for i,future in enumerate(as_completed(tasks),1):
            row=future.result()
            if i%16==0 or not row['valid']:print('PROGRESS '+json.dumps({'completed':i,'total':len(tasks),'job':row['job'],'valid':row['valid'],'error':row.get('error')}),flush=True)
    report=summarize(config,out,client)
    print('PILOT_COMPLETE '+json.dumps(report),flush=True)


if __name__=='__main__':main()
