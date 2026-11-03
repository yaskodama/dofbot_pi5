#!/usr/bin/env python3
# c2_run.py — C-2: the changes C-1 adopted, on the real arm, alternating with the θ just before them
# (protocol ~/paper1_sim2real/protocol/C2_v1.md). Episodes run exactly as in L1 (run_learn.run: sim -> gate -> real).
#
#   python3 learn/c2_run.py point C01          point the fingertip where the cube of C01 goes
#   python3 learn/c2_run.py run C01            one episode with that episode's θ
#   python3 learn/c2_run.py seen C01 ok|ng [note]
#   python3 learn/c2_run.py status
import sys, os, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_learn as RL
import theta as TH

DATA = os.path.expanduser('~/paper1_sim2real/data/c2')
TH0 = {k: v[1] for k, v in TH.SCHEMA.items()}
B06_BEFORE = dict(TH0, survey_inner_cm=12.5, blue_v_min=0.05)
B07_BEFORE = dict(B06_BEFORE, inner_clamp_cm=14.5)
# placement: (color, pos, control θ, treatment θ, source episode)
ARMS = {'H3': ('green', 'H3', TH0, dict(TH0, inner_r_bias_cm=1.0), 'A07'),
        'H2': ('blue', 'H2', TH0, dict(TH0, inner_clamp_cm=14.5), 'A08'),
        'H1': ('green', 'H1', B06_BEFORE, dict(B06_BEFORE, inner_clamp_cm=14.5), 'B06'),
        'P2': ('blue', 'P2', B07_BEFORE, dict(B07_BEFORE, inner_refine_angle=2), 'B07')}
ROUND_A = {'H3': 'T', 'H2': 'C', 'H1': 'T', 'P2': 'C'}            # rounds 1, 4, 5
ROUND_B = {k: 'C' if v == 'T' else 'T' for k, v in ROUND_A.items()}  # rounds 2, 3, 6
SCHED, THETA = [], {}
n = 0
for rnd in range(1, 7):
    pat = ROUND_A if rnd in (1, 4, 5) else ROUND_B
    for key in ('H3', 'H2', 'H1', 'P2'):
        n += 1
        ep = 'C%02d' % n
        color, pos, ctrl, treat, src = ARMS[key]
        arm = pat[key]
        SCHED.append((ep, 'c2' + ('treat' if arm == 'T' else 'ctrl'), color, pos))
        THETA[ep] = treat if arm == 'T' else ctrl

# point run_learn at the C-2 records and schedule
RL.DATA = DATA
RL.EPS = os.path.join(DATA, 'episodes.jsonl')
# re-runs: 'C06r' after a board stop (protocol), 'C11r', 'C11r2', ... until success (addendum c)
SUFFIX = ['r'] + ['r%d' % k for k in range(2, 10)]
RL.SCHED = RL.SCHED + SCHED + [(e + x, m, c, p) for e, m, c, p in SCHED for x in SUFFIX]
for e in list(THETA):
    for x in SUFFIX:
        THETA[e + x] = THETA[e]
_cur = {}
RL.state = lambda: {'theta': dict(THETA[_cur['ep']]), 'adopted': [], 'lessons': []}


def status():
    done = {e['ep']: e for e in RL.episodes()}
    tally = {}
    for ep, mode, c, p in SCHED:
        e = done.get(ep)
        r = '-' if not e else ('ok' if e['success'] else ('ng' if e['success'] is False else 'ran'))
        print('%s %-8s %-5s %s  %s  %s' % (ep, mode, c, p, r, {k: v for k, v in THETA[ep].items() if v != TH0[k]}))
        if e and e['success'] is not None:
            t = tally.setdefault((p, mode), [0, 0]); t[0] += e['success']; t[1] += 1
    for (p, m), (s, k) in sorted(tally.items()):
        print('  %s %-8s %d/%d' % (p, m, s, k))


if __name__ == '__main__':
    os.makedirs(os.path.join(DATA, 'logs'), exist_ok=True)
    cmd = sys.argv[1]
    if cmd in ('point', 'run'):
        _cur['ep'] = sys.argv[2]
        RL.point(sys.argv[2]) if cmd == 'point' else RL.run(sys.argv[2])
    elif cmd == 'seen':
        RL.seen(sys.argv[2], sys.argv[3], ' '.join(sys.argv[4:]))
    elif cmd == 'status':
        status()
