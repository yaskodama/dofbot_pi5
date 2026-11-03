#!/usr/bin/env python3
# c1_summary.py — C-1 tally against the effective changes fixed in protocol C1_v1 (before the runs)
import json, os, sys
from collections import defaultdict
F = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser('~/paper1_sim2real/data/c1/c1.jsonl')


def effective(ep, ch, th):
    """the protocol's 'effective change' sets"""
    if ep == 'A07':
        return ch.get('survey_inner_cm', 99) <= 13.2 or ch.get('inner_r_bias_cm', 0) > 0
    if ep in ('A08', 'B06'):
        gave = {'A08': 13.7, 'B06': 13.3}[ep]
        return ch.get('inner_clamp_cm', 0) > gave or ch.get('inner_r_bias_cm', 0) > 0
    if ep == 'B07':
        return ch.get('inner_refine_angle', 0) >= 1
    return False


rows = defaultdict(list)
for line in open(F):
    r = json.loads(line)
    rows[r['ep']].append(r)
tok_in = tok_out = 0
for ep in sorted(rows):
    rs = sorted(rows[ep], key=lambda r: r['run'])
    good = sum(1 for r in rs if r['adopted'] and effective(ep, r['adopted'], r['theta_before']))
    wrong = sum(1 for r in rs if r['adopted'] and not effective(ep, r['adopted'], r['theta_before']))
    print('%s: effective adopted %d/%d, wrong adopted %d' % (ep, good, len(rs), wrong))
    for r in rs:
        tok_in += sum(u['in'] for u in r['usage']); tok_out += sum(u['out'] for u in r['usage'])
        tr = ' | '.join('%s %s%s' % (t['change'] or '{}', 'PASS' if t.get('pass') else ('-' if t.get('gate') else 'REJECT'),
                                       (' ' + '; '.join(t.get('reasons') or [])[:110]) if not t.get('pass') and t.get('reasons') else '')
                        for t in r['tries'])
        hyp = [h.get('cause') for h in (r['answer'].get('hypotheses') or [])]
        print('   run %d hyp=%s  %s' % (r['run'], hyp, tr))
print('tokens in %d out %d' % (tok_in, tok_out))
