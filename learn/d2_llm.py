#!/usr/bin/env python3
# d2_llm.py — Phase D-2: the LLM's advice on each case, 5 independent runs (protocol ~/paper1_sim2real/protocol/D_v1.md).
#
#   python3 learn/d2_llm.py [N] [EP ...]       default: 5 runs on every recorded case (argue_proto.D_RECORDED)
#   python3 learn/d2_llm.py summary             the change adopted most often per case (= "the LLM's advice")
#
# Same loop as C-1 (c1_replay.one): the advisor prompt with the argument-term instructions (argue_proto.ASK, the same text
# the human's material shows), the logic check and the gate, one revision after a rejection. The arguments of the first
# answer and of the revision are then checked by argue.pl (argue_proto.check_one, tag d2-llm). ADVISOR=openai switches the
# model (D-5 c). Writes data/d2/llm.jsonl; never writes state.json.
import sys, os, json, time, threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import argue_proto as P
import run_learn as RL
from logic import abduce as AB

OUT = os.environ.get('D2_OUT') or os.path.expanduser('~/paper1_sim2real/data/d2/llm.jsonl')
LOCK = threading.Lock()


def model():
    return __import__('openai_advisor').MODEL if os.environ.get('ADVISOR') == 'openai' else RL.MODEL


def one(ep, k, st, e, fx):
    rec = {'ep': ep, 'run': k, 't': time.strftime('%Y-%m-%dT%H:%M:%S'), 'model': model(), 'theta_before': st['theta'],
           'tries': []}
    ans, use = RL.ask_advisor(e, st, extra=P.ASK, fx=fx)
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
            ans2, use2 = RL.ask_advisor(e, st, fx=fx, extra=P.ASK + '\n## Your previous proposal was REJECTED\n'
                                        + json.dumps({'hypotheses': cur.get('hypotheses'), 'change': change})
                                        + '\nReasons: ' + '; '.join(reasons) + '\nPropose again (or no change).\n')
            rec['revision'], cur = ans2, ans2
            rec['usage'].append(use2)
            change = dict(ans2.get('change') or {})
    rec.setdefault('adopted', {})
    print('%s run %d: proposed %s -> adopted %s' % (ep, k, ans.get('change'), rec['adopted']), flush=True)
    return rec


def argued(rec):
    """the argument of the answer that was finally judged (the revision if there was one), checked by argue.pl"""
    a = rec.get('revision') or rec['answer']
    terms = [str(t).strip().rstrip('.') for t in a.get('argument') or []]
    c = P.check_one(rec['ep'], a, '\n'.join(t + '.' for t in terms), 'd2-' + ('openai' if 'gpt' in rec['model'] else 'llm'))
    return {'argument': terms, 'failed_checks': c['failed_checks'], 'text': c['text']}


def key(ch):
    return json.dumps(ch or {}, sort_keys=True)


def summary():
    by = {}
    for l in open(OUT):
        r = json.loads(l)
        by.setdefault((r['ep'], r['model']), []).append(r)
    for (ep, m), rs in sorted(by.items()):
        c = Counter(key(r['adopted']) for r in rs)
        top, n = c.most_common(1)[0]
        print('%s %-16s %d runs  advice %s (%d/%d)  all: %s' % (ep, m, len(rs), top, n, len(rs), dict(c)))


def main():
    a = sys.argv[1:]
    if a[:1] == ['summary']:
        return summary()
    n = int(a.pop(0)) if a and a[0].isdigit() else 5
    eps = a or list(P.D_RECORDED)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    for ep in eps:                                   # one case at a time: context() points run_learn at that case's records
        e, st, fx, extra = P.context(ep)
        with ThreadPoolExecutor(max_workers=n) as ex:
            recs = list(ex.map(lambda k: one(ep, k, st, e, fx), range(1, n + 1)))
        for rec in recs:
            rec.update(argued(rec))
            with open(OUT, 'a') as f:
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    summary()


if __name__ == '__main__':
    main()
