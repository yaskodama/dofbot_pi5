#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# d3_loop.py — Phase D-3 as an advice loop (protocol D_v1 addendum 11/5 17:00, the operator's redesign).
# For each failed case: a control run with the θ it failed with, then a HUMAN loop and an LLM loop, each from that θ:
# advise -> run on the real arm -> the operator's verdict -> advise again ... until success, at most 10 rounds.
#   human: the operator picks simple phrases on the page (advice_form.py /loop); each phrase moves fixed settings by fixed
#          steps (PHRASES, no model in between), or asks for a change of the environment (done by hand).
#   llm:   Claude Opus 5.5 with the loop's prompt, the logic check and the θ gate, one revision after a rejection, exactly as
#          in L1; it sees only the control and its own rounds (never the human's), and may ask for an environment change.
# The human loop comes first (the operator must not see the LLM's advice first). Before the LLM loop the environment is put
# back to the case's condition.
#
#   python3 learn/d3_loop.py start CASE              control θ, place, color from the D-1 record (data/d1)
#   python3 learn/d3_loop.py point CASE
#   python3 learn/d3_loop.py run CASE c|h|l          the control run / the next human / LLM round with the loop's θ now
#   python3 learn/d3_loop.py seen CASE ok|ng [note]  the operator's verdict of the last run (note: not shown to advisors)
#   python3 learn/d3_loop.py llm CASE                ask the LLM for the next round's θ (after a failed run)
#   python3 learn/d3_loop.py status [CASE]
import sys, os, json, re, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_learn as RL
import theta as TH
import d_run as D
from logic import abduce as AB

ROOT = os.path.expanduser('~/paper1_sim2real/data/d3loop')
MAX_ROUNDS = 10
# phrase id -> (Japanese phrase, {setting: ('+', step) | ('*', factor) | ('=', value-if-off then '+', step)}, environment?)
PHRASES = [
    ('wider',       '探す範囲を左右に広く',               {'survey_half_deg': ('+', 10)}),
    ('farther',     '探す範囲を遠くまで',                 {'survey_outer_cm': ('+', 1.0)}),
    ('nearer',      '探す範囲を手前（近く）まで',         {'survey_inner_cm': ('+', -0.5)}),
    ('inner_row',   '手前の列も見回して',                 {'survey_inner_ring_cm': ('on', 14.0, 0.5)}),
    ('dark_blue',   '暗い青も青と見て',                   {'blue_v_min': ('*', 0.5)}),
    ('pale_green',  '淡い緑も緑と見て',                   {'green_s_min': ('+', -0.05)}),
    ('small_blob',  '小さく見える立方体も見逃さないで',   {'min_blob_frac': ('*', 0.67)}),
    ('refine_more', '位置合わせの回数を増やして',         {'refine_rounds': ('+', 2)}),
    ('refine_up',   '位置合わせを強めに',                 {'refine_gain': ('+', 0.1)}),
    ('refine_down', '位置合わせを控えめに',               {'refine_gain': ('+', -0.1)}),
    ('near_keep',   '手前の立方体をあきらめないで',       {'inner_clamp_cm': ('on', 14.5, 0.5)}),
    ('near_far',    '手前の立方体の距離を遠めに読んで',   {'inner_r_bias_cm': ('+', 0.5)}),
    ('reaim',       '寄せた後に向きを合わせ直して',       {'inner_refine_angle': ('+', 1)}),
    ('tilt_fine',   '手首の角度を細かく探して',           {'tilt_step_deg': ('+', -2)}),
    ('undo',        '前の回の変更を元に戻して',           'undo'),
    ('light_on',    '灯りをつけて',                       'env'),
    ('light_down',  '灯りを弱めて',                       'env'),
    ('remove_mat',  '敷物を外して',                       'env'),
]
PH = {p[0]: p for p in PHRASES}
ENV_ASK = """
## This is an advice loop on one case
The robot keeps retrying this same case (same cube, same place) after each of your proposals, until it succeeds (at most
10 rounds). Your earlier rounds on this case are in your memory above. If the failure cannot be fixed by the settings (for
example the cube lies on a surface of its own color, or the light is too dark), you may instead ask for ONE change of the
environment that a person can make by hand: add "environment": "<what to change, in a few words>" to your JSON (the
"change" may then be empty). An environment change counts as a round like a settings change.
"""


def path(*a):
    return os.path.join(ROOT, *a)


def load(case):
    return json.load(open(path('state', case + '.json')))


def save(case, s):
    os.makedirs(path('state'), exist_ok=True)
    json.dump(s, open(path('state', case + '.json'), 'w'), ensure_ascii=False, indent=1)


def rounds_log(rec):
    os.makedirs(ROOT, exist_ok=True)
    with open(path('rounds.jsonl'), 'a') as f:
        f.write(json.dumps(dict(rec, t=time.strftime('%Y-%m-%dT%H:%M:%S')), ensure_ascii=False) + '\n')


def clip(k, v):
    sc = TH.SCHEMA[k]
    v = min(float(sc[3]), max(float(sc[2]), v))
    return int(round(v)) if sc[4] == 'int' else round(v, 3)


def apply_phrases(theta, ids, prev=None):
    """the human's phrases -> the new θ (fixed steps, clipped to the ranges); 'undo' returns to the round before"""
    th, env = dict(theta), []
    for i in ids:
        what = PH[i][2]
        if what == 'undo':
            th = dict(prev or theta)
        elif what == 'env':
            env.append(PH[i][1])
        else:
            for k, op in what.items():
                cur = float(th.get(k, TH.SCHEMA[k][1]))
                if op[0] == '+':
                    th[k] = clip(k, cur + op[1])
                elif op[0] == '*':
                    th[k] = clip(k, cur * op[1])
                elif op[0] == 'on':
                    th[k] = clip(k, op[1] if cur == 0 else cur + op[2])
    return th, env


def all_eps():
    out = []
    for d in ('learn', 'c2', 'c3', 'd1', 'd3loop'):
        f = os.path.join(D.ROOT, d, 'episodes.jsonl')
        if os.path.exists(f):
            out += [json.loads(l) for l in open(f)]
    return out


RECORDED = {'A01': 'learn', 'A02': 'learn', 'B02': 'learn', 'B05': 'learn', 'B07': 'learn', 'C19': 'c2', 'D01': 'c3',
            'K01': 'learn'}       # protocol D_v1: the recorded cases (run with the simulator, as when they failed)


def start(case):
    ds = RECORDED.get(case, 'd1')
    rs = [json.loads(l) for l in open(os.path.join(D.ROOT, ds, 'episodes.jsonl'))]
    e = [x for x in rs if x['ep'] == case][-1]
    if ds == 'd1':
        row = [r for r in D.load('d1')['rows'] if r['ep'] == case][0]
        pos, cond = row['pos'], row.get('condition')
    else:
        pos = e.get('pos') if e.get('pos') in RL.POS and tuple(RL.POS[e['pos']]) == (e['r_cm'], e['base']) \
            else '%g:%d' % (e['r_cm'], e['base'])
        cond = 'recorded (%s, %s %s)' % (ds, e['t_start'][:10], e['t_start'][11:16])
    s = {'case': case, 'color': e['color'], 'pos': pos, 'condition': cond, 'theta0': e['theta'], 'sim': ds != 'd1',
         'arms': {a: {'theta': dict(D.TH0, **e['theta']), 'history': [],
                      'rounds': 0, 'done': None, 'env': []} for a in ('c', 'h', 'l')}}
    save(case, s)
    print('started %s: %s at %s (%s)' % (case, e['color'], pos, cond))


def bind(case, ep, theta):
    s = load(case)
    RL.DATA = ROOT
    RL.EPS = path('episodes.jsonl')
    RL.SCHED = [(ep, 'd3loop', s['color'], D.place(s['pos']))]
    RL.state = lambda: {'theta': dict(theta), 'adopted': [], 'lessons': []}
    RL.ONLY_REAL = not s.get('sim')
    return s


def run(case, arm):
    s = load(case)
    a = s['arms'][arm]
    if a['done']:
        raise SystemExit('%s %s is finished (%s)' % (case, arm, a['done']))
    if arm == 'c' and a['history']:
        raise SystemExit('the control run is done')
    if arm != 'c' and a['rounds'] >= MAX_ROUNDS:
        raise SystemExit('%s %s reached %d rounds' % (case, arm, MAX_ROUNDS))
    if arm != 'c' and not a.get('advised'):
        raise SystemExit('no advice for the next round yet (human: the page; llm: d3_loop.py llm %s)' % case)
    ep = case + ('-c' if arm == 'c' else '-%s%d' % (arm, a['rounds'] + 1))
    if a['env']:
        print('ENVIRONMENT for this run: %s' % ' / '.join(a['env']))
    bind(case, ep, a['theta'])
    RL.run(ep)
    a['last_ep'] = ep
    if arm != 'c':
        a['rounds'] += 1
        a['advised'] = False
    save(case, s)


def seen(case, verdict, note):
    s = load(case)
    arm = next(k for k in ('l', 'h', 'c') if s['arms'][k].get('last_ep') and not s['arms'][k].get('last_seen') == s['arms'][k]['last_ep'])
    a = s['arms'][arm]
    ep = a['last_ep']
    bind(case, ep, a['theta'])
    RL.seen(ep, verdict, '先生の目視: ' + ('成功' if verdict == 'ok' else '失敗'))
    rows = RL.episodes()
    for r in reversed(rows):
        if r['ep'] == ep:
            r['claude_note'] = note; stopped = r.get('board_stopped'); break
    with open(RL.EPS, 'w') as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + '\n' for r in rows)
    a['last_seen'] = ep
    a['history'].append({'ep': ep, 'ok': verdict == 'ok', 'board_stopped': bool(stopped), 'theta': dict(a['theta']), 'env': list(a['env'])})
    if stopped and arm != 'c':
        a['rounds'] -= 1; a['advised'] = True                  # a board stop is not a round: run the same θ again
    elif verdict == 'ok' and arm != 'c':
        a['done'] = 'success in %d rounds' % a['rounds']
    elif arm != 'c' and a['rounds'] >= MAX_ROUNDS:
        a['done'] = 'no success in %d rounds' % MAX_ROUNDS
    if arm == 'c':
        a['done'] = 'reproduced' if verdict != 'ok' else 'not reproduced'
    rounds_log({'case': case, 'arm': arm, 'ep': ep, 'ok': verdict == 'ok', 'board_stopped': bool(stopped),
                'theta': a['theta'], 'env': a['env']})
    save(case, s)
    print('%s %s: %s%s' % (case, ep, verdict, ('  -> ' + a['done']) if a['done'] else ''))


def human(case, ids, free_env=''):
    s = load(case)
    a = s['arms']['h']
    if a['done'] or a.get('advised'):
        raise SystemExit('not waiting for advice')
    prev = a['history'][-2]['theta'] if len(a['history']) >= 2 else s['arms']['c']['theta']
    new, env = apply_phrases(a['theta'], ids, prev)
    if free_env:
        env.append(free_env)
    change = {k: v for k, v in new.items() if a['theta'].get(k) != v}
    a['theta'], a['env'], a['advised'] = new, a['env'] + env, True
    rounds_log({'case': case, 'arm': 'h', 'advice': [PH[i][1] for i in ids], 'free_env': free_env, 'change': change,
                'round': a['rounds'] + 1})
    save(case, s)
    return change, env


def llm(case):
    s = load(case)
    a = s['arms']['l']
    if a['done'] or a.get('advised'):
        raise SystemExit('not waiting for advice')
    eps = [json.loads(l) for l in open(path('episodes.jsonl'))]
    mine = [s['arms']['c'].get('last_ep')] + [h['ep'] for h in a['history']]
    seen_eps = [e for e in eps if e['ep'] in mine]                 # the control and the LLM's own rounds, never the human's
    e = seen_eps[-1]
    st = {'theta': dict(a['theta']), 'lessons': [],
          'adopted': [{'ep': x['ep'], 'change': x['change'], 'why': x.get('why', '')} for x in a.get('adopted', [])]}
    bind(case, e['ep'], a['theta'])
    RL.episodes = lambda: seen_eps
    fx = RL.logic_facts(e, st)
    ans, use = RL.ask_advisor(e, st, extra=ENV_ASK, fx=fx)
    rec = {'case': case, 'arm': 'l', 'round': a['rounds'] + 1, 'after': e['ep'], 'answer': ans, 'usage': [use], 'tries': []}
    cur, change = ans, dict(ans.get('change') or {})
    adopted = {}
    for attempt in (1, 2):
        lg = AB.check(fx, cur)
        if not change:
            rec['tries'].append({'change': {}, 'logic': lg}); break
        new = dict(a['theta']); new.update(change)
        if lg['pass']:
            RL.episodes = all_eps                                  # the gate replays every recorded success, as in L1
            ok, reasons, info = RL.gate(a['theta'], new)
            RL.episodes = lambda: seen_eps
        else:
            ok, reasons = False, ['logic: ' + p for p in lg['problems']]
        rec['tries'].append({'change': change, 'pass': ok, 'reasons': reasons, 'logic': lg})
        if ok:
            adopted = change; break
        if attempt == 1:
            ans2, use2 = RL.ask_advisor(e, st, fx=fx, extra=ENV_ASK + '\n## Your previous proposal was REJECTED\n'
                                        + json.dumps({'hypotheses': cur.get('hypotheses'), 'change': change})
                                        + '\nReasons: ' + '; '.join(reasons) + '\nPropose again (or no change).\n')
            rec['revision'], cur = ans2, ans2
            rec['usage'].append(use2)
            change = dict(ans2.get('change') or {})
    env = (cur.get('environment') or ans.get('environment') or '').strip()
    a['theta'].update(adopted)
    if adopted:
        a.setdefault('adopted', []).append({'ep': e['ep'], 'change': adopted, 'why': cur.get('diagnosis', '')[:300]})
    if env:
        a['env'] = a['env'] + [env]
    a['advised'] = True
    rec.update(adopted=adopted, environment=env)
    rounds_log(rec)
    save(case, s)
    print('%s round %d: proposed %s -> adopted %s%s' % (case, rec['round'], ans.get('change'), adopted,
                                                     ('  ENVIRONMENT: ' + env) if env else ''))


def status(case=None):
    for f in sorted(os.listdir(path('state'))) if os.path.isdir(path('state')) else []:
        s = json.load(open(path('state', f)))
        if case and s['case'] != case:
            continue
        print('%s %s %s (%s)' % (s['case'], s['color'], s['pos'], s['condition']))
        for k, name in (('c', 'control'), ('h', 'human'), ('l', 'LLM')):
            a = s['arms'][k]
            print('  %-7s rounds %-2d %s  %s' % (name, a['rounds'], ' '.join('%s:%s' % (h['ep'], 'ok' if h['ok'] else 'ng')
                                                                       for h in a['history']), a['done'] or ''))


def main():
    a = sys.argv[1:]
    cmd = a[0]
    if cmd == 'start':
        start(a[1])
    elif cmd == 'point':
        s = load(a[1]); bind(a[1], a[1] + '-pt', s['arms']['c']['theta']); RL.point(a[1] + '-pt')
    elif cmd == 'run':
        run(a[1], a[2])
    elif cmd == 'seen':
        seen(a[1], a[2], ' '.join(a[3:]))
    elif cmd == 'llm':
        llm(a[1])
    elif cmd == 'status':
        status(a[1] if len(a) > 1 else None)


if __name__ == '__main__':
    main()
