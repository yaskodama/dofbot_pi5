#!/usr/bin/env python3
# d5_gate.py — Phase D-5 (g): what the θ gate can stop (protocol ~/paper1_sim2real/protocol/D_v1_draft.md, addendum 11/5).
# Never moves the arm, never calls an LLM.
#
# In the records the gate alone never stopped an LLM proposal (logic_only.py gate: 0 of 94). This asks what it CAN stop.
# For each recorded case and each setting of θ, two synthetic proposals: the setting moved to either end of its range.
# Each proposal carries the most favourable diagnosis the logic has for the case (a minimal explanation that names a cause
# tied to that setting, if there is one, each cause claiming the symptoms it explains) — a plausible story with an
# extreme value. Then:
#   logic   abduce.check (as in the loop)
#   gate    run_learn.gate (bounds, geometry, replay of the successful frames the loop had at that case)
#   fix     cf_replay's per-trial verdict on the failed case itself (does it get past the stage where it failed)
#   harm    held-out successes: successful real episodes with archived frames that the gate's replay did NOT use;
#           the same change applied to each one's own θ; harm = found the cube with its own θ, not with the change
#
#   python3 learn/d5_gate.py [EP ...]      default: logic_only.CASES; writes ~/paper1_sim2real/data/d5/gate_value.jsonl
#   python3 learn/d5_gate.py summary
import sys, os, json, collections
from concurrent.futures import ProcessPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import logic_only as LO                    # first: it imports cf_replay (which points run_learn at the right records)

OUT = os.path.join(LO.R, 'd5', 'gate_value.jsonl')


def held_out(ep):
    """successful real episodes with archived frames that the gate's replay for this case does not use"""
    LO.ctx(ep)
    used = {x['ep'] for x in LO.RL.episodes() if x['success']}
    return [x for x in LO.CF.episodes() if x['success'] and x['ep'] not in used
            and os.path.isdir(os.path.join(LO.CF.L.ARCHIVE, x['ep']))]


def own_theta(x):
    return dict(LO.CF.TH0, **(x.get('theta') or {}))


def found(x, th):
    return LO.quiet(LO.cf_verdict, x['ep'], th) == 'passes'


def diagnosis(ep, fx, k):
    """the minimal explanation most favourable to changing k, as an answer the logic check reads"""
    rules = open(LO.AB.RULES).read()
    tied = {c for c, k2, d in LO.re.findall(r'^setting_cause\((\w+),\s*(\w+),\s*(\w+)\)', rules, LO.re.M) if k2 == k}
    expls = LO.explanations(fx, [])
    H = next((h for h in expls if tied & set(h)), expls[0] if expls else [])
    hyps = []
    for c in H:
        claims = []
        for s in fx['symptoms']:
            t = LO.AB._sym_term(s, fx['symptoms'])
            if t is None:
                continue
            out, _ = LO.S.prolog(fx['facts'] + ['hyp(%s).' % h for h in H], '( explains(%s, %s) -> print(yes) ; true )' % (c, t))
            if out and out[0].strip() == 'yes':
                claims.append(s)
        hyps.append({'cause': c, 'explains': claims})
    return H, hyps, bool(tied & set(H))


def one(task):
    ep, k, v, base = task
    e, st, fx, extra = LO.ctx(ep)
    th = dict(st['theta'])
    H, hyps, tied = diagnosis(ep, fx, k)
    new = dict(th); new[k] = v
    lg = LO.AB.check(fx, {'hypotheses': hyps, 'change': {k: v}})
    LO.ctx(ep)                                            # the gate replays this case's successes
    ok, reasons, info = LO.quiet(LO.RL.gate, th, new)
    fix = LO.cf_verdict(ep, new)
    lost = []
    for x in held_out(ep):
        if base.get(x['ep']):                             # found with its own θ
            t2 = own_theta(x); t2[k] = v
            if not found(x, t2):
                lost.append(x['ep'])
    rec = {'ep': ep, 'setting': k, 'from': th.get(k), 'to': v, 'diagnosis': H, 'tied': tied,
           'logic': lg['pass'], 'logic_problems': lg['problems'][:3], 'gate': ok, 'gate_reasons': [r[:160] for r in reasons],
           'fix': fix, 'held_out_lost': lost, 'held_out_n': sum(1 for x in held_out(ep) if base.get(x['ep']))}
    print('%s %s %s->%s logic %s gate %s fix %s lost %d/%d' % (ep, k, rec['from'], v, lg['pass'], ok, fix, len(lost),
                                                              rec['held_out_n']), flush=True)
    return rec


def tasks(eps):
    base = {}
    for ep in eps:                                        # baseline once: does each held-out success replay as found?
        for x in held_out(ep):
            if x['ep'] not in base:
                base[x['ep']] = found(x, own_theta(x))
    out = []
    for ep in eps:
        e, st, fx, extra = LO.ctx(ep)
        for k, sc in LO.TH.SCHEMA.items():
            for v in (sc[2], sc[3]):
                if float(st['theta'].get(k, sc[1])) != float(v):
                    out.append((ep, k, int(v) if sc[4] == 'int' else v, base))
    return out


def summary():
    rs = [json.loads(l) for l in open(OUT)]
    harm = lambda r: bool(r['held_out_lost'])
    c = collections.Counter((r['logic'], r['gate'], harm(r)) for r in rs)
    print('%d proposals (%d cases)' % (len(rs), len({r['ep'] for r in rs})))
    print('logic  gate   harm   n')
    for key in sorted(c, key=str):
        print('%-6s %-6s %-6s %d' % (key + (c[key],)))
    print('harmful (lose a held-out success): %d' % sum(harm(r) for r in rs))
    print('  stopped by gate: %d, by logic: %d, by either: %d, by gate but not logic: %d' % (
        sum(harm(r) and not r['gate'] for r in rs), sum(harm(r) and not r['logic'] for r in rs),
        sum(harm(r) and not (r['gate'] and r['logic']) for r in rs), sum(harm(r) and not r['gate'] and r['logic'] for r in rs)))
    print('passing logic (a plausible story): %d; of these harmful %d, gate stops %d' % (
        sum(r['logic'] for r in rs), sum(r['logic'] and harm(r) for r in rs), sum(r['logic'] and harm(r) and not r['gate'] for r in rs)))
    print('harmless stopped by gate (cost): %d' % sum((not harm(r)) and not r['gate'] for r in rs))


def main():
    a = sys.argv[1:]
    if a[:1] == ['summary']:
        return summary()
    eps = a or LO.CASES
    ts = tasks(eps)
    print('%d proposals' % len(ts), flush=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with ProcessPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 2)) as ex:
        for rec in ex.map(one, ts):
            with open(OUT, 'a') as f:
                f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    summary()


if __name__ == '__main__':
    main()
