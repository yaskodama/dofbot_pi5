#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# advice_form.py — Phase D-2: the human advisor's answer by choices (protocol D_v1 addendum 11/5 16:00, plan C).
# A page on this Mac only (127.0.0.1). Per case the advisor picks: the cause(s) and the causes ruled out, the observations
# used, ONE setting with a direction and a step (a quarter / half / all the way to the end of its range), or no change, or a
# change outside the settings (free text). The JSON the argument check reads is written from the choices to
# data/argue/manual/EP.json. The page shows the same material the LLM gets and nothing of any LLM's answer.
#
#   python3 learn/advice_form.py            then open http://127.0.0.1:8093/
import sys, os, re, json, time, html, urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import argue_form as F
import theta as TH

PORT = 8093
MANUAL = os.path.join(F.P.OUT, 'manual')
STEPS = {'small': (0.25, '少し（範囲の端までの 1/4）'), 'half': (0.5, '中くらい（1/2）'), 'end': (1.0, '範囲の端まで')}
CAUSE_JA = {
    'blob_size_floor_too_high': '立方体とみなす塊の大きさの下限が高すぎる',
    'blue_floor_too_high': '青の明るさの下限が高すぎる（暗い青を捨てる）',
    'green_sat_floor_too_high': '緑の鮮やかさの下限が高すぎる',
    'inner_angle_unrefined': '内側の端で寄せた後、角度を合わせ直していない',
    'inner_edge_unclamped': '内側の端の立方体を寄せずにあきらめる',
    'inner_out_of_view': '内側の立方体が見回しの視野に入らない',
    'inner_radius_underread': '内側の端で距離を近く読みすぎる',
    'refine_overshoot': '位置の補正が行き過ぎる（往復する）',
    'refine_too_weak': '位置の補正が足りない（収まらない）',
    'survey_inner_too_far': '見回しが近い立方体を捨てる限界が遠すぎる',
    'tilt_step_too_coarse': 'つかむ姿勢を探す手首の刻みが粗すぎる',
    'board_stop': '腕の基板の停止（ハードウェア）',
    'grip_miss': '指が立方体の横で閉じた（物理的なずれ）',
    'operator_placement': '置き方・判定の食い違い',
    'unknown': '分からない',
}
SET_JA = {
    'blue_v_min': '青の明るさの下限', 'tilt_step_deg': '手首の刻み（度）', 'inner_clamp_cm': '内側の端で寄せる半径（cm）',
    'min_blob_frac': '塊の大きさの下限（画像に占める割合）', 'green_s_min': '緑の鮮やかさの下限', 'refine_gain': '位置の補正の強さ',
    'refine_rounds': '位置の補正の回数', 'survey_inner_cm': '見回しで捨てる近さの限界（cm）',
    'inner_refine_angle': '寄せた後の角度の合わせ直し（回）', 'inner_r_bias_cm': '近い所の距離の補正（cm）',
    'survey_inner_ring_cm': '内側の見回しの列の半径（cm、0=なし）',
}


def cases():
    return sorted([c for c in F.P.CASES if c.startswith('N') or c in F.P.D_RECORDED], key=lambda c: (not c.startswith('N'), c))


def value(k, cur, d, step):
    sc = TH.SCHEMA[k]
    lo, hi = float(sc[2]), float(sc[3])
    end = hi if d == 'up' else lo
    v = cur + STEPS[step][0] * (end - cur)
    if sc[4] == 'int':
        v = int(round(v))
        if v == cur:
            v = int(min(hi, max(lo, cur + (1 if d == 'up' else -1))))
        return v
    return round(v, 3 if abs(hi - lo) < 1 else 2)


def page(title, body):
    return ('<!doctype html><html lang="ja"><head><meta charset="utf-8"><title>%s</title><style>'
            'body{font-family:-apple-system,"Hiragino Sans",sans-serif;max-width:980px;margin:20px auto;padding:0 16px;line-height:1.6}'
            'table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:3px 8px;font-size:14px;vertical-align:top}'
            'fieldset{margin:14px 0;border:1px solid #aaa;border-radius:6px}legend{font-weight:bold}'
            'pre{background:#f4f4f4;padding:8px;font-size:12px;max-height:340px;overflow:auto;white-space:pre-wrap}'
            '.ok{color:#080}.muted{color:#777}button{font-size:16px;padding:6px 18px}</style></head><body>%s</body></html>'
            % (html.escape(title), body))


def index():
    rows = []
    for c in cases():
        f = os.path.join(MANUAL, c + '.json')        # B05/B06/D01 there are hand transcriptions of the LLM (11/4), not advice
        done = os.path.exists(f) and 'human advisor' in json.load(open(f)).get('source', '')
        kind = '新しい失敗（主解析）' if c.startswith('N') else '記録済み（別に集計）'
        rows.append('<tr><td><a href="/case/%s">%s</a></td><td>%s</td><td>%s</td></tr>'
                    % (c, c, kind, '<span class="ok">記入済み</span>' if done else '―'))
    return page('助言の記入', '<h1>助言の記入（選択式）</h1><p>事例を選んでください。LLM の答えはどこにも表示しません。</p>'
                '<table><tr><th>事例</th><th>区分</th><th>状態</th></tr>%s</table>' % ''.join(rows))


def episode_log(ep):
    m = open(os.path.join(F.OUT, ep + '_material.txt')).read()
    m = m.split('## This episode', 1)[1].split('## Symptoms', 1)[0] if '## This episode' in m else ''
    keep = [l for l in m.splitlines() if not l.startswith('127.0.0.1') or 'locate(real)' in l]
    return '## This episode' + '\n'.join(keep)


def case_page(ep):
    e, fs, prompt = F.facts_of(ep)
    cur = dict(re.match(r'setting\((\w+), (.*)\)$', f).groups() for f in fs if f.startswith('setting('))
    obs = [f for f in fs if f.startswith(('sym(', 'ev('))]
    B = ['<p><a href="/">← 一覧</a></p><h1>事例 %s</h1>' % ep,
         '<p>%s</p>' % ' '.join('<code>%s</code>' % html.escape(f) for f in fs if f.startswith(('color(', 'at('))),
         '<p>材料の全文: <a href="/material_ja/%s" target="_blank">日本語（読み用の写し）</a>　'
         '<span class="muted"><a href="/material/%s" target="_blank">英語の原文（LLM に渡す指示文そのもの）</a></span></p>' % (ep, ep),
         '<details><summary>この回のログ（抜粋）</summary><pre>%s</pre></details>' % html.escape(episode_log(ep)),
         '<form method="post" action="/save/%s"><input type="hidden" name="t_open" value="%d">' % (ep, time.time())]
    B.append('<fieldset><legend>1. 原因（当てはまるものに ✓。複数可）と、考えて退けた原因</legend><table>'
             '<tr><th>原因</th><th>原因とする</th><th>退ける</th></tr>')
    for c in F.CAUSES:
        B.append('<tr><td>%s <span class="muted">%s</span></td><td><input type="checkbox" name="cause" value="%s"></td>'
                 '<td><input type="checkbox" name="ruleout" value="%s"></td></tr>'
                 % (CAUSE_JA.get(c, c), c, c, c))
    B.append('<tr><td>設定の一覧にない原因（自由文）</td><td colspan="2"><input name="cause_free" size="50"></td></tr></table></fieldset>')
    B.append('<fieldset><legend>2. 根拠にした観察（✓）</legend>')
    B += ['<label><input type="checkbox" name="uses" value="%s"> <code>%s</code></label><br>' % (html.escape(f), html.escape(f))
          for f in obs] or ['<p class="muted">（自動で抽出された観察なし）</p>']
    B.append('その他の根拠（自由文）: <input name="uses_free" size="60"></fieldset>')
    B.append('<fieldset><legend>3. 変更（一つ選ぶ）</legend>'
             '<label><input type="radio" name="setting" value="" checked> 変えない</label><br>'
             '<label><input type="radio" name="setting" value="__outside__"> 設定の外の変更（自由文）: </label>'
             '<input name="outside" size="50"><br><table><tr><th></th><th>設定</th><th>今の値</th><th>範囲</th></tr>')
    for k, sc in TH.SCHEMA.items():
        B.append('<tr><td><input type="radio" name="setting" value="%s"></td><td>%s <span class="muted">%s</span></td>'
                 '<td>%s</td><td>%s〜%s</td></tr>' % (k, SET_JA.get(k, k), k, cur.get(k, sc[1]), sc[2], sc[3]))
    B.append('</table>向き: <label><input type="radio" name="dir" value="up" checked> 上げる</label> '
             '<label><input type="radio" name="dir" value="down"> 下げる</label><br>幅: ')
    B += ['<label><input type="radio" name="step" value="%s"%s> %s</label> ' % (s, ' checked' if s == 'half' else '', t)
          for s, (f, t) in STEPS.items()]
    B.append('<p class="muted">値は今の値と範囲から自動で決まります（保存の後に表示）。</p></fieldset>')
    B.append('<fieldset><legend>4. 教訓と、期待する効果（任意・自由文）</legend>教訓: <input name="lesson" size="70"><br>'
             '期待する効果: <input name="effect" size="70"></fieldset>'
             '記入者: <input name="who" value="児玉"> <button type="submit">保存</button></form>')
    return page('事例 ' + ep, ''.join(B))


def save(ep, q):
    g = lambda k: (q.get(k) or [''])[0].strip()
    e, fs, prompt = F.facts_of(ep)
    cur = {k: float(v) for k, v in (re.match(r'setting\((\w+), (.*)\)$', f).groups() for f in fs if f.startswith('setting('))}
    causes, outs, uses = q.get('cause', []), q.get('ruleout', []), q.get('uses', [])
    k, change, outside = g('setting'), {}, ''
    if k == '__outside__':
        outside = g('outside')
    elif k:
        change = {k: value(k, cur.get(k, TH.SCHEMA[k][1]), g('dir'), g('step'))}
    syms = [u[4:-1] for u in uses if u.startswith('sym(')]
    hyps = [{'cause': c, 'explains': syms} for c in causes]
    arg = ['uses(%s)' % u for u in uses] + ['rule_out(%s, [])' % c for c in outs]
    t0 = float(g('t_open') or time.time())
    diag = '; '.join([CAUSE_JA.get(c, c) for c in causes] + ([g('cause_free')] if g('cause_free') else []))
    rec = {'answer': {'diagnosis': diag, 'hypotheses': hyps, 'change': change, 'lesson': g('lesson'), 'effect': g('effect')},
           'argument': arg,
           'choice': {'causes': causes, 'cause_free': g('cause_free'), 'ruled_out': outs, 'uses': uses,
                      'uses_free': g('uses_free'), 'setting': k if k != '__outside__' else None, 'dir': g('dir') if change else None,
                      'step': g('step') if change else None, 'outside': outside},
           'source': 'human advisor (%s), choice form advice_form.py' % g('who'),
           't_open': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(t0)), 't_save': time.strftime('%Y-%m-%dT%H:%M:%S'),
           'minutes': round((time.time() - t0) / 60, 1)}
    os.makedirs(MANUAL, exist_ok=True)
    old = os.path.join(MANUAL, ep + '.json')
    if os.path.exists(old) and 'human advisor' not in json.load(open(old)).get('source', ''):
        os.replace(old, os.path.join(MANUAL, ep + '.llm_transcribed_20261104.json'))   # keep the 11/4 transcription
    json.dump(rec, open(os.path.join(MANUAL, ep + '.json'), 'w'), ensure_ascii=False, indent=1)
    return page('保存しました', '<h1>%s を保存しました</h1><p>原因: %s</p><p>変更: %s</p><p>所要 %.1f 分</p>'
                '<p><a href="/case/%s">直す</a>　<a href="/">一覧へ</a></p>'
                % (ep, html.escape(diag or '―'), html.escape(json.dumps(change, ensure_ascii=False) if change else (outside or '変えない')),
                   rec['minutes'], ep))


class H(BaseHTTPRequestHandler):
    def send(self, text, ctype='text/html; charset=utf-8', code=200):
        b = text.encode('utf-8')
        self.send_response(code); self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(b)))
        self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        p = self.path.split('?')[0]
        try:
            if p == '/':
                return self.send(index())
            m = re.match(r'/(case|material|material_ja)/(\w+)$', p)
            if m and m.group(2) in F.P.CASES:
                if m.group(1) == 'case':
                    return self.send(case_page(m.group(2)))
                suffix = '_material_ja.txt' if m.group(1) == 'material_ja' else '_material.txt'
                return self.send(open(os.path.join(F.OUT, m.group(2) + suffix)).read(), 'text/plain; charset=utf-8')
            self.send('not found', 'text/plain', 404)
        except Exception as x:
            self.send('error: %r' % x, 'text/plain; charset=utf-8', 500)

    def do_POST(self):
        m = re.match(r'/save/(\w+)$', self.path)
        if not (m and m.group(1) in F.P.CASES):
            return self.send('not found', 'text/plain', 404)
        n = int(self.headers.get('Content-Length') or 0)
        self.send(save(m.group(1), urllib.parse.parse_qs(self.rfile.read(n).decode('utf-8'), keep_blank_values=True)))

    def log_message(self, *a):
        pass


if __name__ == '__main__':
    print('http://127.0.0.1:%d/' % PORT, flush=True)
    HTTPServer(('127.0.0.1', PORT), H).serve_forever()
