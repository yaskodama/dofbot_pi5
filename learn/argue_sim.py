#!/usr/bin/env python3
# argue_sim.py — prototype (2026-11-04): how alike two advisors' arguments on the same failure are (logic/sim.pl).
#
#   python3 learn/argue_sim.py [TAG_A TAG_B]      default: manual llm (the latest record of each per case)
#
# Pairs the arguments in data/argue/argue.jsonl case by case. Layers 1-2 run sim.pl on the case's facts; layer 3 runs
# the theory with only one advisor's observations (strict: the sym/ev of its uses/1; closure: the symptoms it cites with
# all the evidence in the logs) and asks whether that derives the other's change; the verdict uses the closure. The chance baseline pairs A's argument on case i with B's on case j (i != j), layer 2 only.
import sys, os, json, re, subprocess, tempfile, itertools
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import argue_proto as P
import theta as TH
from logic import abduce as AB

SIM = os.path.join(HERE, 'logic', 'sim.pl')
OUT = os.path.join(P.OUT, 'sim.jsonl')


def latest(tag):
    r = {}
    for l in open(os.path.join(P.OUT, 'argue.jsonl')):
        x = json.loads(l)
        if x['tag'] == tag:
            r[x['ep']] = x
    return r


def terms(rec):
    t = [x.strip() for x in re.split(r'\.\s*\n', rec['argument'].strip() + '\n') if x.strip()]
    t += ['change(%s, %s)' % (k, AB._val(k, v)) for k, v in (rec['answer'].get('change') or {}).items()]
    return t


def prolog(facts, goal):
    with tempfile.NamedTemporaryFile('w', suffix='.pl', delete=False) as f:
        f.write(':- style_check(-singleton).\n:- style_check(-discontiguous).\n' + '\n'.join(facts) + '\n'); fn = f.name
    out = subprocess.run([AB.SWIPL, '-q', '-g', 'consult(%s), consult(%s), consult(%s), consult(%s), %s, halt' % (
        AB._q(AB.RULES), AB._q(P.ARGUE), AB._q(SIM), AB._q(fn), goal), '-t', 'halt(1)'],
        capture_output=True, text=True, timeout=120)
    os.unlink(fn)
    return out.stdout.splitlines(), out.stderr


RANGES = ['range(%s, %s, %s).' % (k, v[2], v[3]) for k, v in TH.SCHEMA.items()]


def layer12(ctx_facts, ta, tb):
    f = ctx_facts + RANGES + ['arg(a, %s).' % t for t in ta] + ['arg(b, %s).' % t for t in tb]
    out, err = prolog(f, 'sim_report')
    return out


def evidence_of(t):
    """the sym/ev facts an argument cites as its observations"""
    return [m.group(1) + '.' for x in t for m in [re.match(r'uses\(((?:sym|ev)\(.*\))\)$', x)] if m]


def support(ctx_facts, t_from, t_to, closure=False):
    """does the evidence cited in t_from, with the theory, derive every change in t_to.
    strict: only the sym/ev facts t_from cites.  closure: the symptoms t_from cites, with all the evidence in the logs"""
    keep = ('sym(',) if closure else ('sym(', 'ev(')
    cited = [x for x in evidence_of(t_from) if x.startswith('sym(')] if closure else evidence_of(t_from)
    base = [f for f in ctx_facts if not f.startswith(keep)] + cited
    res = []
    for x in t_to:
        m = re.match(r'change\((\w+), ([-\d.]+)\)$', x)
        if m:
            out, _ = prolog(base, '( sim_support(%s, %s) -> write(yes) ; write(no) )' % m.groups())
            res.append(''.join(out).strip() == 'yes')
    return bool(res) and all(res)


def main():
    ta_tag, tb_tag = (sys.argv[1:3] if len(sys.argv) >= 3 else ('manual', 'llm'))
    A, B = latest(ta_tag), latest(tb_tag)
    cases = [ep for ep in P.CASES if ep in A and ep in B]
    ctx = {}
    for ep in cases:
        e, st, fx, extra = P.context(ep)
        ctx[ep] = fx['facts'] + extra
    rows = []
    for ep in cases:
        ta, tb = terms(A[ep]), terms(B[ep])
        l12 = layer12(ctx[ep], ta, tb)
        ab, ba = support(ctx[ep], ta, tb), support(ctx[ep], tb, ta)
        abc, bac = support(ctx[ep], ta, tb, True), support(ctx[ep], tb, ta, True)
        same = 'same_conclusion(yes)' in l12
        eq = abc and bac
        verdict = ('same_reason_same_conclusion' if same and eq else 'diff_reason_same_conclusion' if same else
                   'same_reason_diff_conclusion' if eq else 'different')
        r = {'ep': ep, 'a': ta_tag, 'b': tb_tag, 'layer12': l12, 'a_supports_b': ab, 'b_supports_a': ba,
             'a_supports_b_closure': abc, 'b_supports_a_closure': bac, 'verdict': verdict}
        rows.append(r)
        print('== %s  %s vs %s' % (ep, ta_tag, tb_tag)); print('\n'.join(l12))
        print('strict  A->B', ab, ' B->A', ba, '| closure  A->B', abc, ' B->A', bac); print('verdict:', verdict); print()
    base = []
    for i, j in itertools.permutations(cases, 2):     # chance: A on case i against B on case j
        l12 = layer12(ctx[j], terms(A[i]), terms(B[j]))
        base.append({'a_case': i, 'b_case': j, 'layer12': l12})
        print('baseline %s x %s:' % (i, j), ' '.join(x for x in l12 if not x.startswith('conclusion')))
    with open(OUT, 'a') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
        f.write(json.dumps({'baseline': base, 'a': ta_tag, 'b': tb_tag}, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()
