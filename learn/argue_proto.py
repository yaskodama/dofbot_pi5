#!/usr/bin/env python3
# argue_proto.py — prototype (2026-11-04): the advisor's reasons as Prolog argument terms, checked by logic/argue.pl,
# and the "why the LLM advised that" text generated from the checked terms.
#
#   python3 learn/argue_proto.py manual          check the hand transcriptions of the LLM's earlier free-text diagnoses
#   python3 learn/argue_proto.py ask [N]         ask the LLM again (N runs per case, default 1) for the argument terms
#   python3 learn/argue_proto.py show            the generated text for every checked argument so far
#
# Cases: B05 and B06 (L1, facts exactly as stored with their advice), D01 (C-3, facts rebuilt as in C-4).
# Earlier episodes of every phase give past_at/3 and past_ev/2 (what their logs show), so lessons citing A07 or B09
# can be checked. The episodes that followed give next_sign/2, to score predictions.
import sys, os, json, re, math, time, subprocess, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run_learn as RL
import theta as TH
from logic import abduce as AB

ROOT = os.path.expanduser('~/paper1_sim2real/data')
OUT = os.path.join(ROOT, 'argue')
ARGUE = os.path.join(HERE, 'logic', 'argue.pl')
CASES = {'B05': 'learn', 'B06': 'learn', 'D01': 'c3'}
# Phase D (protocol D_v1): the recorded cases, then the new failures of D-1 (dataset d1) as they come
D_RECORDED = {'A01': 'learn', 'A02': 'learn', 'B02': 'learn', 'B05': 'learn', 'B07': 'learn', 'C19': 'c2', 'D01': 'c3', 'K01': 'learn'}
CASES.update(D_RECORDED)
if os.path.exists(os.path.join(os.path.expanduser('~/paper1_sim2real/data'), 'd1', 'episodes.jsonl')):
    CASES.update({json.loads(x)['ep']: 'd1' for x in open(os.path.expanduser('~/paper1_sim2real/data/d1/episodes.jsonl'))
                  if json.loads(x).get('success') is False and not json.loads(x).get('board_stopped')
                  and not json.loads(x)['ep'].startswith('T')})       # board stops and the trials T01-T05 are not cases
TH0 = {k: v[1] for k, v in TH.SCHEMA.items()}


def rows(ds):
    return [json.loads(x) for x in open(os.path.join(ROOT, ds, 'episodes.jsonl'))]


def use(ds):
    RL.DATA = os.path.join(ROOT, ds)
    RL.EPS = os.path.join(RL.DATA, 'episodes.jsonl')


def ev_of(ds, h):
    use(ds)
    try:
        txt, cs = RL.episode_logs(h, full=True)
        x = AB.extract(h, txt, cs, dict(TH0, **(h.get('theta') or {})), [])
        fin = re.findall(r'-> cube \((-?[\d.]+), (-?[\d.]+)\)', cs)    # where the last camera refinement put the cube
        ref = ['refined(%.1f)' % (100 * math.hypot(float(fin[-1][0]), float(fin[-1][1])))] if fin else []
        return list(dict.fromkeys(x['evidence'] + x['signs'] + ref))
    except Exception:
        return []


def context(ep):
    """facts from the logs, the advisor's state then, and the earlier/later episodes as Prolog facts"""
    ds = CASES[ep]
    e = [x for x in rows(ds) if x['ep'] == ep][-1]
    if ds == 'learn':
        adv = [json.loads(l) for l in open(os.path.join(ROOT, 'learn', 'advice.jsonl'))]
        order = [x['ep'] for x in rows('learn')]
        before = set(order[:order.index(ep)])
        final = json.load(open(os.path.join(ROOT, 'learn', 'state.json')))
        stored = [a for a in adv if a['ep'] == ep]
        th = ({k: float(v) for k, v in (re.match(r'setting\((\w+), ([\d.]+)\)\.', f).groups()
                                         for f in stored[-1]['facts']['facts'] if f.startswith('setting('))}
              if stored else (e.get('theta') or {}))      # pre-phase and control episodes had no advice: θ as recorded
        st = {'theta': dict(TH0, **th),   # settings added later at θ0, as in C-1
              'adopted': [a for a in final['adopted'] if a['ep'] in before],
              'lessons': [l for l in final['lessons'] if l.split(':')[0] in before]}
        RL.episodes = lambda: [x for x in rows('learn') if x['ep'] in before] + [e]
        use(ds)
        fx = RL.logic_facts(e, st)      # rebuilt with today's extraction (the stored facts predate est/1 and clamped/1)
    else:
        import c4_replay as C4
        st, e = C4.use_dataset(ds, ep)
        fx = RL.logic_facts(e, st)
    extra = []
    for d in [x for x in ('learn', 'c2', 'c3', 'd1', 'd3', 'd4') if os.path.exists(os.path.join(ROOT, x, 'episodes.jsonl'))]:   # earlier episodes of every phase
        for h in rows(d):
            if h['t_start'] >= e['t_start'] or h.get('success') is None:
                continue
            q = h['ep'].lower()
            extra.append('past_at(%s, %.1f, %s).' % (q, float(h['r_cm']), h['base']))
            if h['success']:
                extra.append('past_ok(%s).' % q)
            extra += ['past_ev(%s, %s).' % (q, x) for x in ev_of(d, h)]
    later = [h for h in rows(ds) if h['t_start'] > e['t_start']][:2]
    for h in later:
        extra += ['next_sign(%s, %s).' % (h['ep'].lower(), x) for x in ev_of(ds, h)]
        if h.get('success') is False and h.get('held_readbacks') and not h.get('real_placed'):
            extra.append('next_sign(%s, empty_grip).' % h['ep'].lower())
    use(ds)
    return e, st, fx, extra


def run_prolog(fx, extra, arg_text):
    with tempfile.NamedTemporaryFile('w', suffix='.pl', delete=False) as f:
        f.write(':- style_check(-singleton).\n:- style_check(-discontiguous).\n' + '\n'.join(fx['facts'] + extra) + '\n' + arg_text + '\n'); fn = f.name
    out = subprocess.run([AB.SWIPL, '-q', '-g', 'consult(%s), consult(%s), consult(%s), report, argue_report, halt' % (
        AB._q(AB.RULES), AB._q(ARGUE), AB._q(fn)), '-t', 'halt(1)'], capture_output=True, text=True, timeout=120)
    os.unlink(fn)
    return out.stdout.splitlines(), out.stderr.strip()


def hyp_terms(ans, fx):
    """the advisor's hypotheses and change as the facts rules.pl expects (same mapping as abduce.check)"""
    t = []
    for h in ans.get('hypotheses') or []:
        c = str(h.get('cause', '')).strip()
        if c in AB.CAUSES:
            t.append('hyp(%s).' % c)
            for s in h.get('explains') or []:
                k = AB._sym_term(s, fx['symptoms'])
                if k:
                    t.append('claims(%s, %s).' % (c, k))
    for k, v in (ans.get('change') or {}).items():
        t.append('change(%s, %s).' % (k, AB._val(k, v)))
    return t


# ---------------- the generated text (Japanese, for the paper's table) ----------------
JA_CAUSE = {'blue_floor_too_high': '青の明るさの下限が高すぎる', 'inner_edge_unclamped': '内側の端の詰めが無い',
            'tilt_step_too_coarse': '手首の傾きの刻みが粗い', 'survey_inner_too_far': '見回しの限界が外すぎる',
            'inner_radius_underread': '半径を短く読む（補正不足）', 'inner_angle_unrefined': '寄せた後の角度を見直さない',
            'board_stop': '基板の停止', 'grip_miss': 'つかみ損ね', 'operator_placement': '置き方・判定の誤り',
            'blob_size_floor_too_high': '塊の大きさの下限が大きすぎる', 'green_sat_floor_too_high': '緑の彩度の下限が高すぎる',
            'refine_too_weak': '補正が弱い', 'refine_overshoot': '補正が強すぎる', 'inner_out_of_view': '内側が視野の外'}
JA_POLICY = {'below_observed': '観測した最小値のすぐ下', 'restore_true': '教訓の分だけ外へ戻した真の半径',
             'superset_grid': '旧い刻みを含む細かい刻み', 'geometric_limit': '見る姿勢が作れる最も内側（幾何）'}
JA_EFFECT = {'empty_grip': '寄せた後に横へ外す（空振り）', 'false_blue': '緑の近くの暗い雑音を青と誤る'}


def term_ja(t):
    t = t.strip()
    m = re.match(r'ev\(blue_below_floor\((\d+),\s*([\d.]+),\s*([\d.]+)\)\)', t)
    if m: return '青の画素%sが下限で捨てられた（明るさ%s--%s）' % m.groups()
    m = re.match(r'sym\(gave_up_reach\(([\d.]+)\)\)', t)
    if m: return '%s\\,cmであきらめた' % m.group(1)
    m = re.match(r'ev\(grasp_pose_at\(([\d.]+)\)\)', t)
    if m: return '%s\\,cmに掴む姿勢はある' % m.group(1)
    m = re.match(r'sym\(no_grasp\(([\d.]+)\)\)', t)
    if m: return '%s\\,cmで掴む姿勢が見つからない' % m.group(1)
    m = re.match(r'ev\(grasp_ok\(([\d.]+),\s*(\d+)\)\)', t)
    if m: return '%s\\,cmは%s°刻みなら掴める' % m.groups()
    m = re.match(r'past_ev\((\w+),\s*est\(([\d.]+),\s*(\d+)\)\)', t)
    if m: return '%sの推定%s\\,cm' % (m.group(1).upper(), m.group(2))
    m = re.match(r'past_ev\((\w+),\s*refined\(([\d.]+)\)\)', t)
    if m: return '%sの補正後%s\\,cm' % (m.group(1).upper(), m.group(2))
    m = re.match(r'past_ok\((\w+)\)', t)
    if m: return '%sは成功' % m.group(1).upper()
    m = re.match(r'ev\(est\(([\d.]+|_\w*),\s*(\d+)\)\)', t)
    if m: return '見回しの推定が基部%s°' % m.group(2)
    m = re.match(r'at\(([\d.]+),\s*(\d+)\)', t)
    if m: return '真の位置は%s\\,cm・%s°' % m.groups()
    m = re.match(r'past_ev\((\w+),\s*no_grasp\(([\d.]+)\)\)', t)
    if m: return '%sで%s\\,cm掴めず' % (m.group(1).upper(), m.group(2))
    m = re.match(r'no\((.*)\)$', t)
    if m:
        inner = m.group(1)
        if inner.startswith('sym(board_stop'): return '基板は止まっていない'
        if inner.startswith('ev(dropped_inside'): return '限界の内側で捨てた記録が無い'
        if inner.startswith('sym(not_seen'): return '見落としではない'
        if inner.startswith('sym(gave_up_reach'): return 'あきらめた記録が無い'
        return '「%s」が無い' % term_ja(inner)
    m = re.match(r'ge\(([\d.]+),\s*setting\((\w+)\)\)', t)
    if m: return '推定%s\\,cmは%s以上' % (m.group(1), m.group(2).replace('_', '\\_'))
    m = re.match(r'setting\((\w+),\s*([\d.]+)\)', t)
    if m: return '%sは%s' % (m.group(1).replace('_', '\\_'), m.group(2))
    m = re.match(r'sym\((\w+)\)', t)
    if m: return '症状%s' % m.group(1).replace('_', '\\_')
    return t.replace('_', '\\_')


def split_top(s):
    """split a Prolog list body at top-level commas"""
    out, d, cur = [], 0, ''
    for ch in s:
        if ch in '([': d += 1
        if ch in ')]': d -= 1
        if ch == ',' and d == 0:
            out.append(cur); cur = ''
        else:
            cur += ch
    return [x.strip() for x in out + [cur] if x.strip()]


def render(ep, ans, lines):
    """one cell of the table: the checked argument as Japanese sentences, each marked with the logic's verdict"""
    ok = lambda v: '✓' if v in ('ok', 'stated') or v.startswith('came_true') else ('（次の2回では未観測）' if v == 'not_observed' else '✗')
    obs, rej, les, pol, pre, bad = [], [], [], [], [], []
    for l in dict.fromkeys(lines):
        if not l.startswith('check('):
            continue
        parts_ = split_top(l[6:-1])
        item, v = ','.join(parts_[:-1]), parts_[-1]
        if item.startswith('uses('):
            obs.append(term_ja(item[5:-1]) + ok(v))
        elif item.startswith('rule_out('):
            c, why = re.match(r'rule_out\((\w+),\s*\[(.*)\]\)$', item).groups()
            rej.append('%s（%s）%s' % (JA_CAUSE.get(c, c), '、'.join(term_ja(x) for x in split_top(why)), ok(v)))
        elif item.startswith('lesson('):
            m2 = re.match(r'lesson\((\w+),\s*(\w+)\(([^)]*)\),\s*\[(.*)\]\)$', item)
            _, kind, a, sup = m2.groups()
            a = [x.strip() for x in a.split(',')]
            txt = ('実機は内側の端を%s--%s\\,cm短く読む' % tuple(a)) if kind == 'underread' else ('青は明るさ%s--%sまで暗くなる' % tuple(a))
            les.append('「%s」（%sで確認）%s' % (txt, '・'.join(x.strip().upper() for x in sup.split(',')), ok(v)))
        elif item.startswith('value_policy('):
            k, p = re.match(r'value_policy\((\w+),\s*(\w+)', item).groups()
            pol.append('%s%s' % (JA_POLICY.get(p, p), ok(v)))
        elif item.startswith('predict('):
            e2 = re.match(r'predict\((\w+)', item).group(1)
            t = JA_EFFECT.get(e2, e2)
            pre.append(t + ('（%sで的中）' % v[10:-1].upper() if v.startswith('came_true') else '') + ok(v))
        if ok(v) == '✗':
            bad.append('%s → %s' % (item, v))
    hy = '・'.join(JA_CAUSE.get(h['cause'], h['cause']) for h in ans.get('hypotheses') or [])
    ch = '、'.join('%s→%s' % (k, v) for k, v in (ans.get('change') or {}).items())
    probs = [l for l in lines if l.startswith('problem(')]
    parts = ['\\textbf{観察}：' + '。'.join(obs) if obs else '',
             '\\textbf{否定した原因}：' + '。'.join(rej) if rej else '',
             '\\textbf{引いた教訓}：' + '。'.join(les) if les else '',
             '\\textbf{原因}：%s%s。\\textbf{変更}：%s' % (hy, '✓' if not probs else '✗', ch.replace('_', '\\_')),
             '\\textbf{値の方針}：' + '。'.join(pol) if pol else '',
             '\\textbf{予告}：' + '。'.join(pre) if pre else '']
    return '。'.join(p for p in parts if p) + '。', bad + probs


def check_one(ep, ans, arg_text, tag):
    e, st, fx, extra = context(ep)
    full = '\n'.join(hyp_terms(ans, fx)) + '\n' + arg_text
    lines, err = run_prolog(fx, extra, full)
    txt, bad = render(ep, ans, lines)
    rec = {'ep': ep, 'tag': tag, 't': time.strftime('%Y-%m-%dT%H:%M:%S'), 'answer': ans, 'argument': arg_text,
           'prolog': lines, 'stderr': err[:2000], 'text': txt, 'failed_checks': bad}
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, 'argue.jsonl'), 'a') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print('== %s [%s]' % (ep, tag)); print('\n'.join(lines))
    if err: print('stderr:', err[:800])
    print('TEXT:', txt); print('FAILED:', bad or 'none'); print(flush=True)
    return rec


ASK = '''
## Also state your reasons as argument terms (Prolog), checked against the logs
Besides the JSON fields above, add a field "argument": a list of Prolog terms (strings), using ONLY these forms:
- "uses(F)": an observation you rely on. F is one of sym(S), ev(E) from the extracted facts above, setting(K, V),
  or past_ev(Ep, E) for what an earlier episode's logs show (Ep lowercase, E like est(R, Base), gave_up_reach(R),
  dropped_inside(R), no_grasp(R), refined(R) = where the camera refinement ended, blue_below_floor(N, Vlo, Vhi)),
  or past_ok(Ep) (that earlier episode succeeded).
- "rule_out(Cause, [F1, F2, ...])": a cause from the vocabulary you considered and rejected, with the facts that rule it
  out. F may also be no(F) (the fact is absent), ge(Number, setting(K)) or lt(Number, setting(K)).
- "lesson(Id, Rule, [Ep1, Ep2, ...])": a lesson you apply, as a rule checked on the earlier episodes you cite.
  Rule is underread(Lo, Hi) (at the inner edge, the camera reads the cube Lo..Hi cm closer than it is) or
  dim_blue(Vlo, Vhi) (the blue cube's pixels can be as dark as Vlo..Vhi).
- "value_policy(Setting, Policy)": how you chose the new value. Policy is below_observed(Margin) (just below the lowest
  observed value), restore_true(LessonId) (the radius where it gave up, moved out by that lesson's underread),
  superset_grid (a finer step containing every old value) or geometric_limit(Rcm).
- "predict(Effect, [F1, ...])": a side effect you expect later, with its reason. Effect is empty_grip or false_blue.
Give 3-12 terms. Every term is checked; a term whose facts are not in the logs counts against you.
'''


def main():
    a = sys.argv[1:] or ['manual']
    if a[0] == 'manual':
        for ep in CASES:
            p = os.path.join(OUT, 'manual', ep + '.json')
            m = json.load(open(p))
            check_one(ep, m['answer'], '\n'.join(t + '.' for t in m['argument']), 'manual')
    elif a[0] in ('ask', 'ask_openai'):           # ask_openai: D-5 (c), the same prompt to the OpenAI model
        backend, tag = ('openai', 'openai') if a[0] == 'ask_openai' else ('claude', 'llm')
        n = int(a[1]) if len(a) > 1 else 1
        for ep in a[2:] or list(CASES):
            for k in range(n):
                e, st, fx, extra = context(ep)
                ans, usage = RL.ask_advisor(e, st, extra=ASK, fx=fx, backend=backend)
                terms = [str(t).strip().rstrip('.') for t in ans.get('argument') or []]
                rec = check_one(ep, ans, '\n'.join(t + '.' for t in terms), tag)
                print('usage', usage)
    elif a[0] == 'show':
        for l in open(os.path.join(OUT, 'argue.jsonl')):
            r = json.loads(l)
            print(r['ep'], r['tag'], r['text'], r['failed_checks'])


if __name__ == '__main__':
    main()
