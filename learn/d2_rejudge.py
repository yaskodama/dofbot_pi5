# -*- coding: utf-8 -*-
# d2_rejudge.py — re-judge the stored D-2 answers (data/d2) with the current logic and gate, no LLM calls (2026-11-04, after the mixed/3 addendum)
import sys, json, os, io, contextlib, collections
sys.path.insert(0, os.path.expanduser('~/dofbot_pi5/learn'))
import argue_proto as P, run_learn as RL
from logic import abduce as AB
D = os.path.expanduser('~/paper1_sim2real/data/d2/')
res = []
CACHE = {}
for f in ['llm.jsonl', 'openai.jsonl']:
    rows = [json.loads(l) for l in open(D + f)]
    for ep in sorted({r['ep'] for r in rows}):
        with contextlib.redirect_stdout(io.StringIO()):
            e, st, fx, extra = P.context(ep)
        for r in [x for x in rows if x['ep'] == ep]:
            adopted, how = {}, 'none'
            for name, a in [('first', r['answer']), ('revision', r.get('revision'))]:
                if not a or not a.get('change'):
                    if name == 'revision' and a is not None: how = 'revision: no change'
                    continue
                lg = AB.check(fx, a)
                ok = False
                if lg['pass']:
                    key = (ep, json.dumps(a['change'], sort_keys=True))
                    if key not in CACHE:
                        new = dict(st['theta']); new.update(a['change'])
                        CACHE[key] = RL.gate(st['theta'], new)[0]
                        print('gate', key, CACHE[key], file=sys.stderr, flush=True)
                    ok = CACHE[key]
                if ok:
                    adopted, how = a['change'], name; break
                if name == 'first' and r.get('revision') is None: how = 'first rejected, no stored revision'
            res.append({'file': f, 'ep': ep, 'run': r['run'], 'old': r['adopted'], 'new': adopted, 'how': how})
json.dump(res, open(D + 'rejudge_20261104.json', 'w'), ensure_ascii=False, indent=0)
for f in ['llm.jsonl', 'openai.jsonl']:
    for ep in sorted({x['ep'] for x in res}):
        xs = [x for x in res if x['file'] == f and x['ep'] == ep]
        o = collections.Counter(json.dumps(x['old'], sort_keys=True) for x in xs)
        n = collections.Counter(json.dumps(x['new'], sort_keys=True) for x in xs)
        if o != n: print(f, ep, 'old', dict(o), '-> new', dict(n), [x['how'] for x in xs])
print('changed runs:', sum(x['old'] != x['new'] for x in res), '/', len(res))
