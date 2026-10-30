# abduce.py — check the advisor's reasoning with logic before its proposal reaches the θ gate (L1, addendum 2026-10-28b).
#
#   facts(e, real_log, cs_log, theta, history) -> Prolog facts and the list of symptoms (deterministic, from the logs)
#   check(facts, answer) -> {'pass', 'problems', 'explanations', 'refutes', 'symptoms'}   (runs swipl on rules.pl)
#
# The advisor answers with hypotheses [{"cause": <vocabulary>, "explains": [<symptom>...]}] besides its change.
# Everything the logic needs is in the logs; nothing here calls the LLM.
import os, re, json, math, subprocess, tempfile, sys
HERE = os.path.dirname(os.path.abspath(__file__))
RULES = os.path.join(HERE, 'rules.pl')
SWIPL = os.environ.get('SWIPL', '/opt/homebrew/bin/swipl')

CAUSES = {
    'blue_floor_too_high': 'blue_v_min is above the brightness of the blue cube in this light (blue pixels rejected)',
    'green_sat_floor_too_high': 'green_s_min is above the saturation of the green cube in this light',
    'blob_size_floor_too_high': 'min_blob_frac is larger than the cube as seen from the camera',
    'inner_edge_unclamped': 'the estimate fell inside the camera-reachable radius and the robot gave up (inner_clamp_cm off or too small)',
    'survey_inner_too_far': 'the survey (or the go-back look after a glimpse) saw the cube but discarded it because its estimate '
                            'was closer than survey_inner_cm',
    'tilt_step_too_coarse': 'the grasp-pose search skipped the hand tilt that would have worked (tilt_step_deg too large)',
    'refine_too_weak': 'the camera refinement had not converged when it stopped (refine_gain or refine_rounds too small)',
    'refine_overshoot': 'the camera refinement oscillated around the cube (refine_gain too large)',
    'board_stop': 'the arm servo board stopped (hardware)',
    'grip_miss': 'the fingers closed beside the cube although it had been located (physical: slip, push, offset)',
    'operator_placement': 'the cube was not where the schedule says, or the operator verdict disagrees with the logs',
    'unknown': 'none of the above',
}
SYMPTOMS = {
    'not_seen': 'the wanted cube was never found by the camera',
    'gave_up_reach(R)': 'refinement put the cube at R cm where no camera look pose exists, and it gave up',
    'no_grasp(R)': 'the cube was located at R cm but no grasp pose was found',
    'empty_grip': 'the fingers closed on nothing (readback 142-145)',
    'board_stop': 'the arm board stopped during the episode',
    'wrong_zone': 'a cube was placed but not on the right drop-off spot',
    'failed_visual': 'the operator saw a failure that none of the symptoms above shows',
    'risk(blue_floor)': 'not a failure: blue-hued pixels were rejected by the brightness floor somewhere in the survey',
}


INTS = ('tilt_step_deg', 'refine_rounds')


def _num(x):
    return ('%.1f' % x) if isinstance(x, float) else str(x)


def _val(k, v):
    """a setting value as a Prolog number (integer settings as integers, others with their digits kept)"""
    return str(int(round(float(v)))) if k in INTS else repr(float(v))


def real_parts(real_log, cs_log):
    """the real-arm part of the run log and of the locator log"""
    m = real_log.find('== migrate -> Xinu on the DOFBOT')
    real = real_log[m:] if m >= 0 else real_log
    # only the locator's own real-arm lines: the HTTP access lines repeat the PREVIOUS locate's last message at their end
    # (found 2026-10-30 at A09: a give-up from A08 showed up in A09's window)
    cs = '\n'.join(l for l in cs_log.splitlines() if l.lstrip().startswith('locate(real)'))
    return real, cs


def extract(e, real_log, cs_log, theta, history, grasp_ok=None, defaults=None, past_signs=None):
    """facts from the logs. e: the episode record (color, r_cm, base, success, real_placed, board_stopped).
    history: earlier episode records (with their theta). grasp_ok(r_cm, step) -> bool (geometry; None = unknown)"""
    real, cs = real_parts(real_log, cs_log)
    F, sym, ev = [], [], []
    F.append('color(%s).' % e['color'])
    F.append('at(%s, %s).' % (_num(float(e['r_cm'])), e['base']))
    for k, v in theta.items():
        F.append('setting(%s, %s).' % (k, _val(k, v)))
    # evidence
    bb = [(int(n), float(lo), float(hi)) for n, lo, hi in
          re.findall(r'blue-hued px below the value floor: (\d+),? \(?value ([\d.]+)-([\d.]+)', cs)]
    if bb:
        n, lo, hi = max(bb)
        ev.append('blue_below_floor(%d, %.2f, %.2f)' % (n, min(b[1] for b in bb), max(b[2] for b in bb)))
    gave = [(float(r), g) for r, g in re.findall(r'r=([\d.]+) cm is out of reach: no camera look pose \(grasp pose there: (\w+)\)', cs)]
    nog = [float(r) for r in re.findall(r'r=([\d.]+) cm cannot be grasped', cs)]
    for r, g in gave:
        if g == 'yes':
            ev.append('grasp_pose_at(%.1f)' % r)
    for r in nog:
        for s in range(1, 11):
            if grasp_ok and grasp_ok(r, s):
                ev.append('grasp_ok(%.1f, %d)' % (r, s))
    # cubes of this episode's color the survey saw but discarded as closer than its inner limit (addendum c, 2026-10-30)
    lim = float(theta.get('survey_inner_cm', 13.5))
    col = e['color']
    drop = [float(r) for r in re.findall(r'%s\(skip ([\d.]+)cm\)' % col, cs)]
    drop += [float(r) for r in re.findall(r'glimpse dropped: %s at ([\d.]+) cm is inside the survey limit' % col, cs)]
    if 'glimpse confirmed: %s' % col not in cs and 'glimpse dropped: %s' % col not in cs:      # logs from before the drop line existed
        drop += [float(r) for r in re.findall(r'glimpse: %s at ([\d.]+) cm' % col, cs)]
    for r in sorted(set(round(r, 1) for r in drop if r < lim)):
        ev.append('dropped_inside(%.1f)' % r)
    est = [(float(x), float(z)) for x, z in re.findall(r'round \d+: base \d+ look .*?-> cube \((-?[\d.]+), (-?[\d.]+)\)', cs)]
    rounds = theta.get('refine_rounds', 7)
    last = cs[cs.rfind('round 0:'):] if 'round 0:' in cs else ''
    n_last = len(re.findall(r'round \d+: base \d+ look', last))
    if est and n_last >= rounds and len(est) >= 2:
        d = math.hypot(est[-1][0] - est[-2][0], est[-1][1] - est[-2][1]) * 1000
        if d > 10:
            ev.append('refine_unconverged(%d)' % round(d))
    # symptoms
    located = re.search(r'eye\.locate\(real [^)]*\) = (green|blue)', real)
    failed = e.get('success') is False
    if e.get('board_stopped'):
        sym.append('board_stop')
    if failed:
        for r, _ in gave:
            sym.append('gave_up_reach(%.1f)' % r)
        for r in nog:
            sym.append('no_grasp(%.1f)' % r)
        if not located and not gave and not nog:
            sym.append('not_seen')
        if re.search(r'fingers closed on nothing|held=no', real):
            sym.append('empty_grip')
        if (e.get('real_placed') or 0) >= 1:
            sym.append('wrong_zone')
        if not sym:
            sym.append('failed_visual')
    if bb:
        sym.append('risk(blue_floor)')
    sym = list(dict.fromkeys(sym)); ev = list(dict.fromkeys(ev))
    # signs: what the logs show whatever the outcome (a success can contain a give-up that a later sweep recovered from).
    # Used for earlier episodes: a success is evidence against a cause only if that cause's sign is absent (addendum d)
    signs = ['gave_up_reach(%.1f)' % r for r, _ in gave] + ['no_grasp(%.1f)' % r for r in nog]
    signs += [x for x in ev if x.startswith(('dropped_inside(', 'blue_below_floor(', 'refine_unconverged('))]
    if re.search(r'fingers closed on nothing|held=no', real):
        signs.append('empty_grip')
    signs = list(dict.fromkeys(signs))
    F += ['sym(%s).' % s for s in sym] + ['ev(%s).' % x for x in ev]
    for h in history:
        if h.get('success') is None:
            continue
        h = dict(h, theta=dict(defaults or {}, **(h.get('theta') or {})))   # settings added later had their θ0 value then
        F.append('past(%s, %s, %s, %s, %s).' % (h['ep'].lower(), 'ok' if h['success'] else 'ng', h['color'],
                                                _num(float(h['r_cm'])), h['base']))
        for k, v in (h.get('theta') or {}).items():
            F.append('past_setting(%s, %s, %s).' % (h['ep'].lower(), k, _val(k, v)))
        for x in (past_signs or {}).get(h['ep'], []):
            F.append('past_sign(%s, %s).' % (h['ep'].lower(), x))
    return {'facts': F, 'symptoms': sym, 'evidence': ev, 'signs': signs}


def _sym_term(s, known):
    """the advisor's symptom string -> a Prolog term, only if it is one of the extracted symptoms"""
    t = re.sub(r'\s+', '', str(s))
    for k in known:
        if t == k.replace(' ', ''):
            return k
        m1, m2 = re.match(r'(\w+)\(([\d.]+)\)$', t), re.match(r'(\w+)\(([\d.]+)\)$', k)
        if m1 and m2 and m1.group(1) == m2.group(1) and abs(float(m1.group(2)) - float(m2.group(2))) <= 0.15:
            return k
    return None


def check(fx, answer):
    """run the theory on the facts and the advisor's answer. Returns the verdict and the logic's own explanations."""
    pre = []
    A = list(fx['facts'])
    hyps = answer.get('hypotheses') or []
    for h in hyps:
        c = str(h.get('cause', '')).strip()
        if c not in CAUSES:
            pre.append('not_a_cause(%s)' % json.dumps(c)); continue
        A.append('hyp(%s).' % c)
        for s in h.get('explains') or []:
            t = _sym_term(s, fx['symptoms'])
            if t is None:
                pre.append('unsupported_claim(%s,%s): no such symptom in the logs' % (c, json.dumps(str(s))))
            else:
                A.append('claims(%s, %s).' % (c, t))
    for k, v in (answer.get('change') or {}).items():
        if not re.match(r'^[a-z_]+$', k) or not isinstance(v, (int, float)):
            pre.append('change_unsupported(%s): not a numeric setting' % json.dumps(k)); continue
        A.append('change(%s, %s).' % (k, _val(k, v)))
    if not hyps and fx['symptoms'] and any(not s.startswith('risk') for s in fx['symptoms']):
        pre.append('no hypotheses given')
    with tempfile.NamedTemporaryFile('w', suffix='.pl', delete=False) as f:
        f.write(':- style_check(-singleton).\n' + '\n'.join(A) + '\n'); fn = f.name
    try:
        out = subprocess.run([SWIPL, '-q', '-g', 'consult(%s), consult(%s), report, halt' % (
            _q(RULES), _q(fn)), '-t', 'halt(1)'], capture_output=True, text=True, timeout=60)
    finally:
        os.unlink(fn)
    if out.returncode != 0:
        raise RuntimeError('swipl: ' + out.stderr[-800:])
    problems, expl, refutes = list(pre), [], []
    for line in out.stdout.splitlines():
        line = line.strip()
        if line.startswith('problem('):
            problems.append(line[len('problem('):-1])
        elif line.startswith('explanation('):
            expl.append(line[len('explanation('):-1])
        elif line.startswith('refutes('):
            refutes.append(line[len('refutes('):-1])
    problems = list(dict.fromkeys(problems))
    return {'pass': not problems, 'problems': problems, 'explanations': list(dict.fromkeys(expl)),
            'refutes': list(dict.fromkeys(refutes)), 'symptoms': fx['symptoms'], 'evidence': fx['evidence']}


def _q(p):
    return "'" + p.replace("'", "\\'") + "'"


def prompt_text(fx):
    """the vocabulary and the extracted symptoms, for the advisor's prompt"""
    return ('## Symptoms extracted from the logs (deterministic)\n' + (', '.join(fx['symptoms']) or '(none)') +
            '\nMeaning: ' + '; '.join('%s = %s' % kv for kv in SYMPTOMS.items()) +
            '\n## Causes you may name (vocabulary)\n' + '\n'.join('- %s: %s' % kv for kv in CAUSES.items()))
