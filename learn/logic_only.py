#!/usr/bin/env python3
# logic_only.py — two analyses a reviewer asked for (2026-11-04). Never moves the arm, never calls an LLM.
#
#   python3 learn/logic_only.py gate      (a) what stopped each proposal in the records (logic or the θ gate), and what the
#                                             θ gate alone would have done with the proposals the logic stopped
#   python3 learn/logic_only.py advise    (b) a logic-only advisor: every minimal explanation of rules.pl, and for each cause
#                                             tied to a setting the smallest step from the current value that the theory
#                                             accepts as removing it (supported/2). Compared with the LLMs' advice (data/d2),
#                                             all through the same θ gate and the per-trial replay of cf_replay.py.
# Output: ~/paper1_sim2real/data/logic_only/{gate,advise}.json
import sys, os, json, re, io, contextlib, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cf_replay as CF                     # first: it imports c3_run, which points run_learn at C-3's records
import argue_proto as P
import run_learn as RL
import theta as TH
from logic import abduce as AB
import argue_sim as S

R = os.path.expanduser('~/paper1_sim2real/data')
OUT = os.path.join(R, 'logic_only')
FILES = ['learn/advice.jsonl', 'c1/c1.jsonl', 'c4/c4.jsonl', 'd2/llm.jsonl', 'd2/openai.jsonl']
P.CASES.update({'A07': 'learn', 'A08': 'learn', 'B04': 'learn'})
CASES = ['A01', 'A02', 'A07', 'A08', 'B02', 'B04', 'B05', 'B06', 'B07', 'C19', 'D01', 'K01']


def quiet(f, *a):
    with contextlib.redirect_stdout(io.StringIO()):
        return f(*a)


def ctx(ep):
    return quiet(P.context, ep)


# ---------------- (a) what stopped the proposals ----------------

def gate_stats():
    out = {'by_file': {}, 'logic_stopped': []}
    for f in FILES:
        c = collections.Counter()
        for l in open(os.path.join(R, f)):
            r = json.loads(l)
            for t in r.get('tries', []):
                if not t.get('change'):
                    c['no change'] += 1
                elif t.get('pass'):
                    c['adopted'] += 1
                elif all(x.startswith('logic:') for x in t.get('reasons') or []):
                    c['logic'] += 1
                    out['logic_stopped'].append({'file': f, 'ep': r['ep'], 'change': t['change']})
                else:
                    c['gate'] += 1
        out['by_file'][f] = dict(c)
    seen = {}
    for x in out['logic_stopped']:                      # the θ gate alone on what the logic stopped
        key = (x['ep'], json.dumps(x['change'], sort_keys=True))
        if key not in seen:
            e, st, fx, extra = ctx(x['ep'])
            new = dict(st['theta']); new.update(x['change'])
            ok, reasons, _ = quiet(RL.gate, st['theta'], new)
            seen[key] = {'pass': ok, 'reasons': reasons}
            print('gate alone', key, ok, reasons[:1], flush=True)
        x.update(seen[key])
    out['logic_stopped_gate_alone'] = collections.Counter(x['pass'] for x in out['logic_stopped'])
    return out


# ---------------- (b) the logic-only advisor ----------------

def grid(k, cur, d):
    lo, hi = TH.SCHEMA[k][2], TH.SCHEMA[k][3]
    step = 1 if TH.SCHEMA[k][4] == 'int' else (0.01 if hi <= 1.0 else 0.1)
    n = int(round((hi - lo) / step))
    vals = [round(lo + i * step, 4) for i in range(n + 1)]
    vals = [v for v in vals if (v > cur if d == 'up' else v < cur)]
    return sorted(vals, key=lambda v: abs(v - cur))


def explanations(fx, extra):
    out, _ = S.prolog(fx['facts'] + extra, 'forall(minimal_explanation(H), (print(H), nl))')
    return [re.findall(r'\w+', h) for h in out if h.startswith('[')]


def smallest_step(fx, extra, H, k, cur, d):
    vals = grid(k, cur, d)
    if not vals:
        return None
    goal = 'member(V, [%s]), supported(%s, V) -> print(V) ; true' % (', '.join(map(str, vals)), k)
    hy = ['hyp(%s).' % c for c in H]
    out, _ = S.prolog(fx['facts'] + extra + hy, '( ' + goal + ' )')
    # member/2 walks the list in order: the first supported value is the smallest step
    return float(out[0]) if out and out[0].strip() else None


def logic_advice(ep):
    e, st, fx, extra = ctx(ep)
    rules = open(AB.RULES).read()
    sc = re.findall(r'^setting_cause\((\w+),\s*(\w+),\s*(\w+)\)', rules, re.M)
    expls = explanations(fx, extra)
    cands = []
    for H in expls:
        for c in H:
            for c2, k, d in sc:
                if c2 == c:
                    v = smallest_step(fx, extra, H, k, float(st['theta'][k]), d)
                    if v is not None:
                        rng = TH.SCHEMA[k][3] - TH.SCHEMA[k][2]
                        cands.append({'expl': H, 'cause': c, 'change': {k: int(v) if TH.SCHEMA[k][4] == 'int' else v},
                                      'size': abs(v - float(st['theta'][k])) / rng})
    # the advisor: act if any explanation names a setting; among those, the smallest normalized step (then by name)
    pick = sorted(cands, key=lambda x: (x['size'], json.dumps(x['change'])))[0]['change'] if cands else {}
    return e, st, expls, cands, pick


def modal(f, ep):
    try:
        rs = [json.loads(l) for l in open(os.path.join(R, f)) if json.loads(l)['ep'] == ep]
    except OSError:
        return None
    if not rs:
        return None
    c = collections.Counter(json.dumps(r['adopted'], sort_keys=True) for r in rs)
    k, n = c.most_common(1)[0]
    return {'change': json.loads(k), 'n': n, 'of': len(rs)}


def cf_verdict(ep, th):
    """cf_replay's per-trial verdict for this failed episode under θ = th"""
    e = [x for x in CF.episodes() if x['ep'] == ep][-1]
    CF.STAR = th
    th0 = dict(CF.TH0, **(e.get('theta') or {}))
    sw = CF.real_sweeps(e)
    fr = [CF.survey(e, s, th) for s in sw]
    paths = [CF.star_path(r) for r in fr if r]
    for l in CF.cs_lines(e):
        m = re.search(r'glimpse (confirmed|dropped): (\w+) at ([\d.]+) cm', l)
        if m and m.group(2) == e['color']:
            paths.append(CF.star_path(CF.rebias(float(m.group(3)), th0, th)))
    gl = [l for l in CF.cs_lines(e) if re.search(r'glimpse: %s at' % e['color'], l)]
    found = any(p.endswith(', grasp pose') for p in paths)
    if ep in CF.GRIP:
        return 'grip: found, not replayable' if found else 'does not pass'
    return ('passes' if found else
            'undetermined (glimpse only)' if gl and th['survey_inner_ring_cm'] > 0 else 'does not pass')


def advise():
    rows = []
    for ep in CASES:
        e, st, expls, cands, pick = logic_advice(ep)
        row = {'ep': ep, 'explanations': expls, 'candidates': cands, 'logic_only': pick,
               'claude': modal('d2/llm.jsonl', ep), 'gpt': modal('d2/openai.jsonl', ep), 'theta_before': st['theta']}
        verdicts = {}
        for name in ('logic_only', 'claude', 'gpt'):
            ch = row[name] if name == 'logic_only' else (row[name] or {}).get('change')
            if ch is None:
                continue
            new = dict(st['theta']); new.update(ch)
            ctx(ep)                                      # the gate replays this case's past
            g = quiet(RL.gate, st['theta'], new)[0] if ch else None
            verdicts[name] = {'change': ch, 'gate': g, 'cf': cf_verdict(ep, new)}
        row['verdicts'] = verdicts
        rows.append(row)
        print(ep, 'expl', expls, '| logic-only', pick, '|', {k: (v['change'], v['gate'], v['cf']) for k, v in verdicts.items()}, flush=True)
    return rows


def main():
    os.makedirs(OUT, exist_ok=True)
    what = sys.argv[1]
    res = gate_stats() if what == 'gate' else advise()
    json.dump(res, open(os.path.join(OUT, what + '.json'), 'w'), ensure_ascii=False, indent=1, default=str)


if __name__ == '__main__' and sys.argv[1:] != ['candidates']:
    main()


# ---------------- (b2) every candidate of the logic, and the loop's own adoptions then ----------------
LOOP = {'B04': ('learn/advice.jsonl', 'B04'), 'B05': ('learn/advice.jsonl', 'B05'), 'B06': ('learn/advice.jsonl', 'B06'),
        'A07': ('c1/c1.jsonl', 'A07'), 'A08': ('c1/c1.jsonl', 'A08'), 'B07': ('c1/c1.jsonl', 'B07'), 'D01': ('c4/c4.jsonl', 'D01'),
        'C19': ('c4/c4.jsonl', 'C19')}


def loop_adopted(f, ep):
    rs = [json.loads(l) for l in open(os.path.join(R, f)) if json.loads(l)['ep'] == ep]
    ad = [t['change'] for r in rs for t in r.get('tries', []) if t.get('pass')]
    c = collections.Counter(json.dumps(r.get('adopted') or next((t['change'] for t in r.get('tries', []) if t.get('pass')), {}),
                                       sort_keys=True) for r in rs)
    k, n = c.most_common(1)[0]
    return {'change': json.loads(k), 'n': n, 'of': len(rs)}


def candidates_all():
    rows = []
    for ep in CASES:
        e, st, expls, cands, pick = logic_advice(ep)
        uniq = list({json.dumps(c['change'], sort_keys=True): c for c in cands}.values())
        res = []
        for c in uniq:
            new = dict(st['theta']); new.update(c['change'])
            ctx(ep)
            g = quiet(RL.gate, st['theta'], new)[0]
            res.append({'cause': c['cause'], 'change': c['change'], 'gate': g, 'cf': cf_verdict(ep, new)})
        loop = None
        if ep in LOOP:
            loop = loop_adopted(*LOOP[ep])
            new = dict(st['theta']); new.update(loop['change'])
            loop['cf'] = cf_verdict(ep, new) if loop['change'] else cf_verdict(ep, dict(st['theta']))
        rows.append({'ep': ep, 'candidates': res, 'loop': loop})
        print(ep, [(r['change'], r['gate'], r['cf']) for r in res], '| loop', loop, flush=True)
    return rows


if __name__ == '__main__' and sys.argv[1:] == ['candidates']:
    json.dump(candidates_all(), open(os.path.join(OUT, 'candidates.json'), 'w'), ensure_ascii=False, indent=1, default=str)
