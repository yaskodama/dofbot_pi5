#!/usr/bin/env python3
# c4_replay.py — C-4: do the two fixes C-3 needed (tilt_step_deg 1, survey_inner_ring_cm) come out of the advice loop?
# Offline, like C-1 (protocol ~/paper1_sim2real/protocol/C4_v1.md).
#
#   python3 learn/c4_replay.py facts              the extracted symptoms / evidence and the logic-only explanations (no LLM)
#   python3 learn/c4_replay.py [N] [EP ...]       N independent advice runs per episode (default 5; D01 C19 C13r2)
#
# Each run sees the state just before that episode: θ in force then, the adoptions and lessons of L1, the earlier
# episodes of the same experiment (C-2 or C-3), and only their successful episodes in the gate's replay.
# Same model and prompt as run_learn.advise (one revision after a rejection). Never writes state.json.
import sys, os, json, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_learn as RL
import theta as TH
from logic import abduce as AB

OUT = os.path.expanduser('~/paper1_sim2real/data/c4/c4.jsonl')
DATASET = {'D01': 'c3', 'C19': 'c2', 'C13r2': 'c2'}
ROOT_DATA = os.path.expanduser('~/paper1_sim2real/data')
TH0 = {k: v[1] for k, v in TH.SCHEMA.items()}


def use_dataset(name, ep):
    RL.DATA = os.path.join(ROOT_DATA, name)
    RL.EPS = os.path.join(RL.DATA, 'episodes.jsonl')
    rows = [json.loads(x) for x in open(RL.EPS)]
    e = [x for x in rows if x['ep'] == ep][-1]
    past = [x for x in rows if x['t_start'] < e['t_start'] and x.get('success') is not None]
    RL.episodes = lambda: past + [e]
    final = json.load(open(os.path.join(ROOT_DATA, 'learn', 'state.json')))
    st = {'theta': dict(TH0, **(e.get('theta') or {})), 'adopted': final['adopted'], 'lessons': final['lessons']}
    return st, e


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
    with open(OUT, 'a') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print('%s run %d: proposed %s -> adopted %s' % (ep, k, ans.get('change'), rec['adopted']), flush=True)
    return rec


def main():
    args = sys.argv[1:]
    if args and args[0] == 'facts':
        for ep, ds in DATASET.items():
            st, e = use_dataset(ds, ep)
            fx = RL.logic_facts(e, st)
            lg = AB.check(fx, {'hypotheses': [], 'change': {}})
            print(ep, ds, 'symptoms', fx['symptoms'], '\n   evidence', fx['evidence'], '\n   logic-only', lg.get('explanations'))
        return
    n = int(args.pop(0)) if args and args[0].isdigit() else 5
    eps = args or list(DATASET)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    for ep in eps:                                    # sequential: the gate and the geometry use the global TH.OVERRIDE
        st, e = use_dataset(DATASET[ep], ep)
        fx = RL.logic_facts(e, st)
        for k in range(1, n + 1):
            try:
                one(ep, k, st, e, fx)
            except Exception as x:                    # e.g. the API credit runs out: record it and stop
                with open(OUT, 'a') as f:
                    f.write(json.dumps({'ep': ep, 'run': k, 'error': repr(x)[:500]}) + '\n')
                print('%s run %d: ERROR %r' % (ep, k, x)); return


if __name__ == '__main__':
    main()
