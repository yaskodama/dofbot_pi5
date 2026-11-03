#!/usr/bin/env python3
# c3_run.py — C-3: every change adopted so far, together, plus the inner survey row, on the real arm
# (protocol ~/paper1_sim2real/protocol/C3_v1.md). Episodes run exactly as in L1 (run_learn.run: sim -> gate -> real).
#
#   python3 learn/c3_run.py point D01          point the fingertip where the cube of D01 goes
#   python3 learn/c3_run.py run D01            one episode with θ*
#   python3 learn/c3_run.py seen D01 ok|ng [note]
#   python3 learn/c3_run.py status
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_learn as RL
import theta as TH

DATA = os.path.expanduser('~/paper1_sim2real/data/c3')
TH0 = {k: v[1] for k, v in TH.SCHEMA.items()}
# θ*: L1 Phase B's three (B04 survey 12.5, B05 blue 0.05, B06 clamp 14.5), C-1/C-2's two (refine_angle 2, r_bias 1.0),
# and the inner survey row at 14 cm (from the C-2 logs, not from the advisor)
THETA_STAR = dict(TH0, survey_inner_cm=12.5, blue_v_min=0.05, inner_clamp_cm=14.5,
                  inner_refine_angle=2, inner_r_bias_cm=1.0, survey_inner_ring_cm=14.0)
THETA_V1 = dict(THETA_STAR)                                  # D01 ran with this (tilt_step_deg 5 = θ0)
THETA_STAR['tilt_step_deg'] = 1                              # addendum a (2026-11-03): 5 deg steps leave no grasp pose near 14.2 cm
PLAN = [('green', 'H3'), ('blue', 'H1'), ('green', 'H2'), ('blue', 'H4'), ('green', 'P2'), ('blue', 'P5'),
        ('blue', 'H3'), ('green', 'H1'), ('blue', 'H2'), ('green', 'H4'), ('blue', 'P2'), ('green', 'P1')]
SCHED = [('D%02d' % (i + 1), 'c3', c, p) for i, (c, p) in enumerate(PLAN)]
SUFFIX = ['r'] + ['r%d' % k for k in range(2, 10)]          # device-side stops are re-run until success (protocol)
RL.DATA = DATA
RL.EPS = os.path.join(DATA, 'episodes.jsonl')
RL.SCHED = RL.SCHED + SCHED + [(e + x, m, c, p) for e, m, c, p in SCHED for x in SUFFIX]
RL.state = lambda: {'theta': dict(THETA_STAR), 'adopted': [], 'lessons': []}


def status():
    done = {e['ep']: e for e in RL.episodes()}
    for ep, mode, c, p in SCHED:
        tries = [done[k] for k in [ep] + [ep + x for x in SUFFIX] if k in done]
        r = ' '.join('%s:%s' % (e['ep'], {True: 'ok', False: 'ng', None: 'ran'}[e['success']]) for e in tries) or '-'
        print('%s %-5s %s  %s' % (ep, c, p, r))
    first = [done[ep] for ep, *_ in SCHED if ep in done and done[ep]['success'] is not None]
    print('first attempts: %d/%d' % (sum(e['success'] for e in first), len(first)))


if __name__ == '__main__':
    os.makedirs(os.path.join(DATA, 'logs'), exist_ok=True)
    cmd = sys.argv[1]
    if cmd == 'point':
        RL.point(sys.argv[2])
    elif cmd == 'run':
        RL.run(sys.argv[2])
    elif cmd == 'seen':
        RL.seen(sys.argv[2], sys.argv[3], ' '.join(sys.argv[4:]))
    elif cmd == 'status':
        status()
