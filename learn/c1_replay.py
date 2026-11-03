#!/usr/bin/env python3
# c1_replay.py — C-1: re-judge failed learn episodes with the improved loop, offline (protocol ~/paper1_sim2real/protocol/C1_v1.md)
#
#   python3 learn/c1_replay.py [N] [EP ...]      N independent advice runs per episode (default 5; A07 A08 B06 B07)
#
# Each run sees the state just before that episode, rebuilt from the records: θ in force then (settings added later at θ0),
# the adoptions and lessons before it, the episodes before it, and only earlier successful episodes in the gate's replay.
# Same model and prompt as run_learn.advise (one revision after a rejection). Never writes state.json.
import sys, os, json, time, threading
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_learn as RL
import theta as TH
from logic import abduce as AB

OUT = os.environ.get('C1_OUT') or os.path.expanduser('~/paper1_sim2real/data/c1/c1.jsonl')
LOCK = threading.Lock()                  # the gate and the geometry use the global TH.OVERRIDE
ALL = RL.episodes()


def before(ep):
    return [x for x in ALL if x['ep'] < ep and x['ep'][0] in 'AB']


def state_before(ep, final):
    th0 = {k: v[1] for k, v in TH.SCHEMA.items()}
    e = [x for x in ALL if x['ep'] == ep][-1]
    return {'theta': dict(th0, **(e.get('theta') or {})),
            'adopted': [a for a in final['adopted'] if a['ep'] < ep],
            'lessons': [l for l in final['lessons'] if l.split(':')[0] < ep]}, e


def one(ep, k, st, e, fx):
    rec = {'ep': ep, 'run': k, 't': time.strftime('%Y-%m-%dT%H:%M:%S'), 'model': RL.MODEL, 'theta_before': st['theta'],
           'tries': []}
    ans, use = RL.ask_advisor(e, st, fx=fx)
    rec['answer'], rec['usage'] = ans, [use]
    cur, change = ans, dict(ans.get('change') or {})
    for attempt in (1, 2):
        lg = AB.check(fx, cur)
        if not change:
            rec['tries'].append({'change': {}, 'logic': lg, 'gate': 'no change proposed'}); break
        new = dict(st['theta']); new.update(change)
        if lg['pass']:
            with LOCK:
                ok, reasons, info = RL.gate(st['theta'], new)
        else:
            ok, reasons, info = False, ['logic: ' + p for p in lg['problems']], {}
        rec['tries'].append({'change': change, 'pass': ok, 'reasons': reasons, 'info': info, 'logic': lg,
                             'hypotheses': cur.get('hypotheses')})
        if ok:
            rec['adopted'] = change; break
        if attempt == 1:
            ans2, use2 = RL.ask_advisor(e, st, fx=fx, extra='\n## Your previous proposal was REJECTED\n'
                                        + json.dumps({'hypotheses': cur.get('hypotheses'), 'change': change})
                                        + '\nReasons: ' + '; '.join(reasons) + '\nPropose again (or no change).\n')
            rec['revision'], cur = ans2, ans2
            rec['usage'].append(use2)
            change = dict(ans2.get('change') or {})
    rec.setdefault('adopted', {})
    with LOCK:
        with open(OUT, 'a') as f:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print('%s run %d: proposed %s -> adopted %s' % (ep, k, ans.get('change'), rec['adopted']), flush=True)
    return rec


def main():
    args = sys.argv[1:]
    n = int(args.pop(0)) if args and args[0].isdigit() else 5
    eps = args or ['A07', 'A08', 'B06', 'B07']
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    final = RL.state()
    jobs = []
    for ep in eps:
        st, e = state_before(ep, final)
        RL.episodes = (lambda ep=ep: before(ep) + [x for x in ALL if x['ep'] == ep])
        fx = RL.logic_facts(e, st)
        jobs += [(ep, k, st, e, fx) for k in range(1, n + 1)]
    # every view of the records (history, gate replay) is the past of the episode this thread works on
    TLS = threading.local()
    RL.episodes = lambda: before(TLS.ep) + [x for x in ALL if x['ep'] == TLS.ep]
    def run_job(job):
        TLS.ep = job[0]
        return one(*job)
    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(run_job, jobs))


if __name__ == '__main__':
    main()
