#!/usr/bin/env python3
# argue_form.py — the human advisor's entry form for Phase D (protocol D_v1 addendum 11/4): argument terms picked from lists.
#
#   python3 learn/argue_form.py EP [EP ...]      writes ~/paper1_sim2real/data/argue/forms/EP.md
#
# The form shows the same facts the LLM gets (the case, the settings with their ranges, the extracted symptoms and evidence,
# what earlier episodes' logs show) and nothing it does not: no LLM output, and no next_sign (the episodes after the case).
# Each line is a ready-made term; the advisor ticks lines, fills the blanks (…) and copies the chosen terms into the
# JSON at the end, which argue_proto.py checks exactly as it checks the LLM's (data/argue/manual/EP.json).
import sys, os, re, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import argue_proto as P
import theta as TH
from logic import abduce as AB

OUT = os.path.join(P.OUT, 'forms')
RULES = open(AB.RULES).read()
CAUSES = sorted(set(re.findall(r'^setting_cause\((\w+),', RULES, re.M)) | set(re.findall(r'^other_cause\((\w+)\)', RULES, re.M)))
CAUSE_SETTING = {}
for c, k, d in re.findall(r'^setting_cause\((\w+),\s*(\w+),\s*(\w+)\)', RULES, re.M):
    CAUSE_SETTING.setdefault(c, []).append('%s %s' % (k, {'up': '↑', 'down': '↓'}[d]))
PAST_KEEP = ('est(', 'refined(', 'gave_up_reach(', 'dropped_inside(', 'no_grasp(', 'blue_below_floor(', 'empty_grip',
             'survey_row_missed(', 'refine_unconverged(', 'clamped(')


def facts_of(ep):
    e, st, fx, extra = P.context(ep)
    return e, [f.rstrip('.') for f in fx['facts'] + extra if not f.startswith('next_sign(')], P.RL.advisor_prompt(e, st, P.ASK, fx=fx)


def form(ep):
    e, fs, prompt = facts_of(ep)
    pick = lambda p: [f for f in fs if f.startswith(p)]
    L = ['# 助言の記入用紙 %s' % ep, '',
         '記入者: ＿＿＿＿  日付: ＿＿＿＿  所要: ＿＿分（LLM の出力は見ないこと）', '',
         '材料: 同じフォルダの `%s_material.txt` は LLM に渡す指示文そのもの（ログ・設定・それまでの記録・教訓・抽出した事実）。'
         'この用紙はそれを項の形で選びやすく並べ直したもの。' % ep, '',
         '## 1. 事例', '']
    L += ['- `%s`' % f for f in pick('color(') + pick('at(')]
    L += ['', '## 2. 今の調整値（範囲）', '', '| 設定 | 今の値 | 範囲 | 意味 |', '|---|---|---|---|']
    cur = dict(re.match(r'setting\((\w+), (.*)\)$', f).groups() for f in pick('setting('))
    for k, v in TH.SCHEMA.items():
        L.append('| %s | %s | %s〜%s | %s |' % (k, cur.get(k, v[1]), v[2], v[3], v[5]))
    L += ['', '## 3. 根拠にする観察（使うものに ✓。`uses(F)`）', '']
    L += ['- [ ] `uses(%s)`' % f for f in pick('sym(') + pick('ev(')]
    L += ['- [ ] `uses(setting(…, …))`（上の表から）', '- [ ] `uses(past_ev(…, …))`・`uses(past_ok(…))`（下の 6 から）', '',
          '## 4. 原因（一つ以上を原因に、考えて退けたものは理由と一緒に）', '',
          '| 原因 | 対応する設定と向き | 原因とする | 退ける（理由の事実を書く） |', '|---|---|---|---|']
    for c in CAUSES:
        L.append('| %s | %s | [ ] | [ ] `rule_out(%s, [ … ])` |' % (c, '、'.join(CAUSE_SETTING.get(c, ['（設定外）'])), c))
    L += ['', '理由に書ける事実: 上の観察、`past_ev(Ep, E)`、`past_ok(Ep)`、`no(F)`（その事実が無い）、'
          '`ge(数, setting(K))`・`lt(数, setting(K))`。', '',
          '## 5. 教訓・値の決め方・予告', '',
          '- [ ] `lesson(Id, underread(Lo, Hi), [Ep, …])`：内側の端でカメラが立方体を Lo〜Hi cm 近く読む',
          '- [ ] `lesson(Id, dim_blue(Vlo, Vhi), [Ep, …])`：青の画素の明るさが Vlo〜Vhi まで落ちる',
          '- [ ] `value_policy(K, below_observed(余裕))`：観察された最小値の少し下',
          '- [ ] `value_policy(K, restore_true(教訓Id))`：あきらめた半径を教訓の分だけ外へ',
          '- [ ] `value_policy(K, superset_grid)`：古い値をすべて含む細かい刻み',
          '- [ ] `value_policy(K, geometric_limit(R))`：幾何の限界 R cm',
          '- [ ] `predict(empty_grip, [ … ])`・`predict(false_blue, [ … ])`：後で出ると思う副作用と理由',
          '', '## 6. それまでのエピソードのログ（成否・置き場所・主な証拠）', '',
          '| 回 | 成否 | 置き場所 | 証拠 |', '|---|---|---|---|']
    eps = []
    for f in pick('past_at('):
        x, r, b = re.match(r'past_at\((\w+), ([\d.]+), (\d+)\)$', f).groups()
        eps.append((x, r, b))
    for x, r, b in eps:
        ok = '成功' if ('past_ok(%s)' % x) in fs else '失敗'
        ev = [m.group(1) for f in fs for m in [re.match(r'past_ev\(%s, (.*)\)$' % x, f)] if m and m.group(1).startswith(PAST_KEEP)]
        L.append('| %s | %s | %s cm, %s° | %s |' % (x, ok, r, b, ', '.join(ev) or '―'))
    L += ['', '## 7. 写し（ここに選んだ項を入れ、data/argue/manual/%s.json に保存）' % ep, '', '```json',
          json.dumps({'answer': {'diagnosis': '…（自由文で短く）',
                                 'hypotheses': [{'cause': '…', 'explains': ['…']}],
                                 'change': {'…設定': '…値'}},
                      'argument': ['uses(…)', 'rule_out(…, […])', 'lesson(…)', 'value_policy(…, …)', 'predict(…, […])'],
                      'source': 'human advisor, form %s' % ep}, ensure_ascii=False, indent=1), '```', '']
    return '\n'.join(L), prompt


def main():
    os.makedirs(OUT, exist_ok=True)
    for ep in sys.argv[1:] or list(P.CASES):
        p = os.path.join(OUT, ep + '.md')
        text, prompt = form(ep)
        open(p, 'w').write(text)
        open(os.path.join(OUT, ep + '_material.txt'), 'w').write(prompt)
        print(p)


if __name__ == '__main__':
    main()
