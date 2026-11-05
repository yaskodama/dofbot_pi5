#!/usr/bin/env python3
# d_run.py — Phase D on the real arm (protocol ~/paper1_sim2real/protocol/D_v1.md): D-1 collect failures, D-3 the three
# arms per case (control / human / LLM), D-4 θ0 / θ*6 / θ*7 interleaved. Episodes run exactly as in L1 and C-3
# (run_learn.run: sim -> gate -> real); only the θ and the place come from the stage's plan (data/<stage>/plan.json).
#
#   python3 learn/d_run.py plan d4                         the D-4 plan from data/d4/order.json (d4_order.py)
#   python3 learn/d_run.py add d1 N01 blue 21:45 theta_star7 [condition ...]   one D-1 episode (place = H1.. or R:BASE)
#   python3 learn/d_run.py plan d3 [SEED]                  the D-3 plan from data/d3/cases.json (control first, then
#                                                          human and LLM in a random order; one run when they agree)
#   python3 learn/d_run.py point|run STAGE EP              (a re-run after a board stop is EPr, EPr2, ...)
#   python3 learn/d_run.py seen STAGE EP ok|ng [note]
#   python3 learn/d_run.py sim STAGE EP|all on|off         run these rows with the simulator and its gate (default: real only)
#   python3 learn/d_run.py status STAGE                    the arm / θ is hidden (D-3, D-4) unless REVEAL=1
import sys, os, json, re, random
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_learn as RL
import theta as TH

ROOT = os.path.expanduser('~/paper1_sim2real/data')
TH0 = {k: v[1] for k, v in TH.SCHEMA.items()}
# θ*7 = C-3's θ* (c3_run.THETA_STAR); θ*6 = the six the loop adopted, without the inner survey row the designer added
THETAS = {'theta0': dict(TH0),
          'theta_star7': dict(TH0, survey_inner_cm=12.5, blue_v_min=0.05, inner_clamp_cm=14.5, inner_refine_angle=2,
                              inner_r_bias_cm=1.0, survey_inner_ring_cm=14.0, tilt_step_deg=1)}
THETAS['theta_star6'] = dict(THETAS['theta_star7'], survey_inner_ring_cm=0.0)
SUFFIX = re.compile(r'r\d*$')
# From N05 (protocol D_v1 addendum 11/5 14:40) the simulator run and its gate are skipped: since 10/27 it passed 130 of 130
# and the agent's behaviour on the real arm does not depend on it. SIM=1 brings it back for a run.
RL.ONLY_REAL = os.environ.get('SIM') != '1'


def plan_path(stage):
    return os.path.join(ROOT, stage, 'plan.json')


def load(stage):
    try:
        return json.load(open(plan_path(stage)))
    except OSError:
        return {'stage': stage, 'rows': []}


def save(stage, p):
    os.makedirs(os.path.join(ROOT, stage, 'logs'), exist_ok=True)
    json.dump(p, open(plan_path(stage), 'w'), ensure_ascii=False, indent=1)


def place(pos):
    if pos in RL.POS:
        return pos
    r, b = pos.split(':')                     # a place outside the named ones, e.g. 21:45 (cm, base deg)
    RL.POS[pos] = (float(r), int(b))
    return pos


def row_of(stage, ep):
    base = SUFFIX.sub('', ep) if not any(r['ep'] == ep for r in load(stage)['rows']) else ep
    for r in load(stage)['rows']:
        if r['ep'] == base:
            return r
    raise SystemExit('no episode %s in the %s plan' % (ep, stage))


def bind(stage, ep):
    """point run_learn at this stage's records, and give it this episode's place and θ"""
    r = row_of(stage, ep)
    RL.DATA = os.path.join(ROOT, stage)
    RL.EPS = os.path.join(RL.DATA, 'episodes.jsonl')
    RL.SCHED = [(ep, stage, r['color'], place(r['pos']))]       # mode = the stage, never 'control' (that forces θ0)
    RL.state = lambda: {'theta': dict(r['theta']), 'adopted': [], 'lessons': []}
    RL.ONLY_REAL = not (r.get('sim') or os.environ.get('SIM') == '1')    # a row marked sim (or SIM=1) runs the simulator too
    return r


def note(stage, ep, r):
    with open(os.path.join(ROOT, stage, 'arms.jsonl'), 'a') as f:     # which case / arm / θ each episode was
        f.write(json.dumps({'ep': ep, **{k: r.get(k) for k in ('case', 'arm', 'theta_name', 'condition', 'block')}},
                           ensure_ascii=False) + '\n')


def plan_d4():
    o = json.load(open(os.path.join(ROOT, 'd4', 'order.json')))
    rows = [{'ep': x['id'], 'color': x['color'], 'pos': x['pos'], 'theta_name': x['theta'], 'theta': THETAS[x['theta']],
             'block': x['block']} for x in o['rows']]
    save('d4', {'stage': 'd4', 'seed': o['seed'], 'rows': rows})
    print('d4: %d episodes' % len(rows))


def plan_d3(seed):
    """cases.json: {CASE: {color, pos, theta (the θ it failed with), human: {setting: value}, llm: {...}}}"""
    cases = json.load(open(os.path.join(ROOT, 'd3', 'cases.json')))
    rng = random.Random(seed)
    rows = []
    # episode ids are neutral (Y01, Y02, ...): the operator is told only the id and the place, never the arm
    # (protocol D_v1 addendum 11/5, one expert). The arm stays in the plan and in arms.jsonl.
    for c in sorted(cases):
        x = cases[c]
        rows.append({'ep': c + 'c', 'case': c, 'arm': 'control', 'color': x['color'], 'pos': x['pos'], 'theta': x['theta']})
        h, l = x.get('human') or {}, x.get('llm') or {}
        arms = [('human+llm', h)] if h == l else [('human', h), ('llm', l)]
        rng.shuffle(arms)
        for name, ch in arms:
            rows.append({'ep': c + {'human': 'h', 'llm': 'l', 'human+llm': 'hl'}[name], 'case': c, 'arm': name,
                         'color': x['color'], 'pos': x['pos'], 'theta': dict(x['theta'], **ch), 'change': ch})
    for k, r in enumerate(rows, 1):
        r['ep'] = 'Y%02d' % k
        # recorded cases (L1 / C-3, run with the simulator) are re-run with it; new D-1 cases (N.., T..) without
        # (protocol D_v1 addendum 11/5 14:50, the operator's choice)
        r['sim'] = not r['case'].startswith(('N', 'T'))
    save('d3', {'stage': 'd3', 'seed': seed, 'rows': rows})
    print('d3: %d cases, %d episodes' % (len(cases), len(rows)))


def status(stage):
    eps = {}
    try:
        for l in open(os.path.join(ROOT, stage, 'episodes.jsonl')):
            e = json.loads(l); eps[e['ep']] = e
    except OSError:
        pass
    for r in load(stage)['rows']:
        tries = [eps[k] for k in eps if SUFFIX.sub('', k) == r['ep'] or k == r['ep']]
        res = ' '.join('%s:%s' % (e['ep'], {True: 'ok', False: 'ng', None: 'ran'}[e['success']]) for e in tries) or '-'
        arm = (r.get('theta_name') or r.get('arm') or '') if os.environ.get('REVEAL') == '1' or stage == 'd1' else '(hidden)'
        print('%-6s %-5s %-6s %-12s %-8s %-4s %s' % (r['ep'], r['color'], r['pos'], arm, r.get('condition') or '',
                                                  'sim' if r.get('sim') else '', res))


def main():
    a = sys.argv[1:]
    cmd = a[0]
    if cmd == 'plan':
        plan_d4() if a[1] == 'd4' else plan_d3(int(a[2]) if len(a) > 2 else 20261110)
    elif cmd == 'add':
        stage, ep, color, pos, th = a[1:6]
        p = load(stage)
        assert not any(r['ep'] == ep for r in p['rows']), 'already planned: ' + ep
        place(pos)
        p['rows'].append({'ep': ep, 'color': color, 'pos': pos, 'theta_name': th, 'theta': THETAS[th],
                          'condition': ' '.join(a[6:])})
        save(stage, p)
        print('added', p['rows'][-1]['ep'], color, pos, th, ' '.join(a[6:]))
    elif cmd == 'point':
        bind(a[1], a[2]); RL.point(a[2])
    elif cmd == 'run':
        r = bind(a[1], a[2]); note(a[1], a[2], r); RL.run(a[2])
    elif cmd == 'seen':
        # the advisors read 'visual': it holds the operator's verdict only. Anything else (the assistant's reading of the
        # logs) goes to claude_note, which no advisor sees (protocol D_v1 addendum 11/5 16:10)
        bind(a[1], a[2]); RL.seen(a[2], a[3], '先生の目視: ' + ('成功' if a[3] == 'ok' else '失敗'))
        rows = RL.episodes()
        for r in reversed(rows):
            if r['ep'] == a[2]:
                r['claude_note'] = ' '.join(a[4:]); break
        with open(RL.EPS, 'w') as f:
            f.writelines(json.dumps(r, ensure_ascii=False) + '\n' for r in rows)
    elif cmd == 'sim':                                     # sim STAGE EP|all on|off: mark rows to run with the simulator
        p = load(a[1])
        for r in p['rows']:
            if a[2] in ('all', r['ep']):
                r['sim'] = a[3] == 'on'
        save(a[1], p)
        print('sim', a[3], a[2])
    elif cmd == 'status':
        status(a[1] if len(a) > 1 else 'd1')


if __name__ == '__main__':
    main()
