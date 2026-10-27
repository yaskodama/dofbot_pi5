#!/usr/bin/env python3
# run_learn.py — the real robot learns its settings θ from an LLM's advice (paper ① RQ5, real-robot version).
# Protocol: ~/paper1_sim2real/protocol/L1_v1.md
#
#   python3 learn/run_learn.py point <ep> [k]        point the fingertip where the cube of episode <ep> goes
#   python3 learn/run_learn.py run <ep>              one episode with the θ in force (sim -> gate -> real, as in E0m)
#   python3 learn/run_learn.py seen <ep> ok|ng [note] operator's visual verdict (decides success)
#   python3 learn/run_learn.py advise <ep>           (learn episodes only) LLM diagnosis -> proposal -> θ gate -> adopt or reject
#   python3 learn/run_learn.py status                schedule, results so far, θ in force
#
# θ lives in data/learn/state.json between episodes. During a run it is written to learn/theta.json (read by locate.py)
# and removed afterwards, so E0m and every other run keep the human-tuned values.
import sys, os, time, json, re, subprocess, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
import theta as TH
import locate as L
from logic import abduce as AB

DATA = os.path.expanduser('~/paper1_sim2real/data/learn')
EPS = os.path.join(DATA, 'episodes.jsonl')
STATE = os.path.join(DATA, 'state.json')
ADVICE = os.path.join(DATA, 'advice.jsonl')
CSLOG = os.path.join(ROOT, 'color_service.log')
MODEL = 'claude-opus-5-5'

POS = {'P1': (17, 90), 'P2': (15, 70), 'P3': (20, 110), 'P4': (17, 55), 'P5': (20, 125),
       'H2': (15, 110), 'H3': (14.5, 90)}          # (cm from the base axis, base deg); H* = near the inner edge
PRE_A = [('blue', 'P2'), ('green', 'H3'), ('blue', 'H2'), ('green', 'P2'), ('blue', 'P4')]
LEARN_A = [('blue', 'P2'), ('green', 'H3'), ('blue', 'H2'), ('green', 'P1'), ('blue', 'P3'),
           ('green', 'P2'), ('blue', 'H3'), ('green', 'H2'), ('blue', 'P5'), ('green', 'P4')]
SCHED = ([('A%02d' % (i + 1), 'pre', c, p) for i, (c, p) in enumerate(PRE_A)] +
         [('A%02d' % (i + 6), 'learn', c, p) for i, (c, p) in enumerate(LEARN_A)] +
         [('A%02d' % (i + 16), 'post', c, p) for i, (c, p) in enumerate(PRE_A)])
# Phase B (a new condition, decided before B01 and appended to the protocol) is added here then.


def sched(ep):
    for e in SCHED:
        if e[0] == ep:
            return e
    raise SystemExit('no episode %s in the schedule' % ep)


def state():
    try:
        return json.load(open(STATE))
    except (OSError, ValueError):
        return {'theta': {k: v[1] for k, v in TH.SCHEMA.items()}, 'adopted': [], 'lessons': []}   # Phase A starts at θ0


def save_state(s):
    os.makedirs(DATA, exist_ok=True)
    json.dump(s, open(STATE, 'w'), indent=1, ensure_ascii=False)


def episodes():
    try:
        return [json.loads(x) for x in open(EPS)]
    except OSError:
        return []


def point(ep, k=1):
    _, _, color, pos = sched(ep)
    r, base = POS[pos]
    s = L.point_pose(r / 100.0)
    L.move(base, s, 2500, 30)
    print('episode %s: put the %s cube under the fingertip (%s: %.1f cm, base %d deg)' % (ep, color, pos, r, base))


def run(ep):
    from run_e0m import check_zone, cam_on
    _, mode, color, pos = sched(ep)
    st = state()
    r, base = POS[pos]
    os.makedirs(os.path.join(DATA, 'logs'), exist_ok=True)
    log = os.path.join(DATA, 'logs', '%s.log' % ep)
    summ = os.path.join(DATA, 'logs', '%s.json' % ep)
    TH.write(st['theta'], ep)                              # θ in force for this episode (locate.py reads it)
    try:
        L.move(90, [90, 90, 90], 2000, 30)
        time.sleep(2.2)
        ver0 = L.arm_udp('ver', tries=3)
        cs0 = os.path.getsize(CSLOG) if os.path.exists(CSLOG) else 0
        t0 = time.time()
        with open(log, 'w') as f:
            try:
                rc = subprocess.run([sys.executable, '-u', os.path.join(ROOT, 'agent', 'dock.py'), '--cubes', color,
                                     '--at', '%s:%s:%d' % (color, r, base), '--summary', summ],
                                    stdout=f, stderr=subprocess.STDOUT, timeout=1500).returncode
            except subprocess.TimeoutExpired:
                rc = 'timeout'
        t1 = time.time()
        cs1 = os.path.getsize(CSLOG) if os.path.exists(CSLOG) else 0
    finally:
        TH.clear()
    txt = open(log, errors='ignore').read()
    try:
        s = json.load(open(summ))
    except (OSError, ValueError):
        s = {'placed': {}, 'gate': None}
    real_part = txt.split('== migrate', 1)[1] if '== migrate' in txt else ''
    try:
        held = json.loads(urllib.request.urlopen('http://localhost:8091/held?since=%f' % t0, timeout=5).read())
    except OSError:
        held = []
    ver1 = L.arm_udp('ver', tries=3)
    stopped = ('0.-1' in ver1) or ver1 == ''
    if stopped:
        zone = 'skipped (board stopped)'
    else:
        cam_on()
        zone = check_zone(150 if color == 'green' else 30, os.path.join(DATA, 'logs', '%s_zone.ppm' % ep))
        L.move(90, [90, 90, 90], 2500, 30)
    g = s.get('gate') or {}
    rec = {'ep': ep, 'mode': mode, 'color': color, 'pos': pos, 'r_cm': r, 'base': base,
           't_start': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(t0)), 'minutes': round((t1 - t0) / 60, 2),
           'theta': st['theta'], 'dock_rc': rc, 'sim_placed': s['placed'].get('sim'), 'gate_pass': g.get('pass'),
           'real_placed': s['placed'].get('real'), 'held_readbacks': [v for _, v in held],
           'zone_seen': zone, 'camera_success': zone == color, 'board_stopped': stopped,
           'board_before': ver0, 'board_after': ver1, 'cslog': [cs0, cs1], 'log': os.path.basename(log),
           'visual': None, 'success': None}
    with open(EPS, 'a') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print(json.dumps(rec, ensure_ascii=False, indent=1))


def seen(ep, verdict, note):
    rows = episodes()
    for r in reversed(rows):
        if r['ep'] == ep:
            r['visual'] = verdict + ((' ' + note) if note else ''); r['success'] = verdict == 'ok'; break
    else:
        raise SystemExit('no episode %s' % ep)
    with open(EPS, 'w') as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + '\n' for r in rows)
    print('episode %s: success=%s' % (ep, verdict == 'ok'))


# ---------------- the advisor ----------------

TASK = """The robot is a 6-axis desktop arm (DOFBOT) whose controller is a Raspberry Pi 5 running a bare-metal OS.
Task of one episode: one 3 cm cube (green or blue) lies on the table 13-21 cm from the arm's base axis.
The robot must put green cubes on the right drop-off spot and blue cubes on the left one.
How it works: (1) survey: the wrist camera looks at 8 spots (16 cm and 21 cm from the base, 4 directions each) and
finds color blobs; (2) refine: it re-aims the camera at the blob up to N rounds, moving the estimate toward where the
camera says the cube is; (3) grasp: it computes a grasp pose by inverse kinematics, lowers, closes the fingers to 145 and
reads the finger servo back (139-140 = holding a cube, 142-145 = empty); (4) carries the cube to the drop-off spot.
The task program (the agent) and the hardware are fixed. You can change ONLY the settings listed below."""


def settings_text(theta):
    out = []
    for k, (_, _, lo, hi, kind, desc) in TH.SCHEMA.items():
        out.append('- %s = %s  (range %s..%s, %s): %s' % (k, theta[k], lo, hi, kind, desc))
    return '\n'.join(out)


def history_text(st, upto):
    lines = []
    for e in episodes():
        if e['ep'] == upto:
            break
        lines.append('%s [%s] %s cube at %.1f cm, base %d deg -> %s%s' % (
            e['ep'], e['mode'], e['color'], e['r_cm'], e['base'], 'success' if e['success'] else 'FAILURE',
            ' (arm board stopped)' if e['board_stopped'] else ''))
    for a in st['adopted']:
        lines.append('after %s: adopted %s (because: %s)' % (a['ep'], a['change'], a['why'][:200]))
    return '\n'.join(lines) or '(none)'


def episode_logs(e, full=False):
    txt = open(os.path.join(DATA, 'logs', e['log']), errors='ignore').read()
    real = txt.split('== migrate', 1)[1] if '== migrate' in txt else txt
    a, b = e['cslog']
    cs = ''
    if os.path.exists(CSLOG) and b > a:
        with open(CSLOG, 'rb') as f:
            f.seek(a); cs = f.read(b - a).decode('utf-8', 'ignore')
    cs = '\n'.join(l for l in cs.splitlines() if 'not answering' not in l and 'back off' not in l)
    if full:
        return txt, cs
    return real[-6000:], cs[-9000:]


def grasp_ok(r_cm, step):
    """geometry for the logic: is there a grasp pose at r_cm when the hand tilt is searched in `step` deg steps"""
    L.load_geo()
    keep = dict(TH.OVERRIDE)
    TH.OVERRIDE['tilt_step_deg'] = step
    try:
        return bool(L.grasp_poses(r_cm / 100.0)[1])
    finally:
        TH.OVERRIDE.clear(); TH.OVERRIDE.update(keep)


def logic_facts(e, st, hints=True):
    """facts for the logic check (addendum 2026-10-28b), from the same logs the advisor reads"""
    txt, cs = episode_logs(e, full=True)
    if not hints:
        txt, cs = plain(txt), plain(cs)
    hist = [x for x in episodes() if x['ep'] < e['ep'] and x['ep'][0] == e['ep'][0]]
    return AB.extract(e, txt, cs, st['theta'], hist, grasp_ok=grasp_ok)


PLAIN = [r' \(blue-hued px below the value floor: [^)]*\)', r', ?blue-hued px below the value floor: [^,\n]*',
         r'blue-hued px below the value floor: [^,\n]*', r': no camera look pose \(grasp pose there: \w+\)',
         r': no grasp pose with hand tilt 180\.\.130 deg in \d+ deg steps', r' r=[\d.]+ cm']


def plain(text):
    """the log without the three diagnostic hints added for L1 (protocol L1_v1, 2026-10-28 addendum 2)"""
    for pat in PLAIN:
        text = re.sub(pat, '', text)
    return re.sub(r'(survey \d+ cm base \d+: )(?=\n|$)', r'\1nothing', text)   # what the survey line said before the hint existed


def ask_advisor(e, st, extra='', hints=True, fx=None):
    import anthropic
    real, cs = episode_logs(e)
    if not hints:
        real, cs = plain(real), plain(cs)
    fx = fx or logic_facts(e, st, hints)
    prompt = f"""{TASK}

## Settings you may change (current values)
{settings_text(st['theta'])}

## Your memory: earlier episodes and the changes adopted after them
{history_text(st, e['ep'])}

## Lessons you wrote earlier
{chr(10).join('- ' + x for x in st['lessons']) or '(none)'}

## This episode: {e['ep']}
Cube: {e['color']} at {e['r_cm']} cm from the base axis, base angle {e['base']} deg (90 = straight ahead).
Outcome (the operator's visual check): {'SUCCESS' if e['success'] else 'FAILURE'} — {e['visual']}
Arm board stopped during the episode: {e['board_stopped']}. Finger readbacks after closing: {e['held_readbacks']}.

### Run log of the real arm (agent and dock)
{real}

### Camera/locator service log for this episode
{cs}

{AB.prompt_text(fx)}
{extra}
## What to answer
Diagnose this episode from the logs. Then decide whether changing the settings would make FUTURE episodes succeed more
often. Change at most 2 settings, and only if the logs show evidence that a setting caused or risked the failure.
Do not change settings to explain hardware stops or a misplaced cube. A change that fixes one case must not break others.
State your explanation as hypotheses: causes from the vocabulary above, each with the extracted symptoms it explains.
Every failure symptom must be explained, no hypothesis should be superfluous, and every setting you change must be the
one a hypothesis blames. Your hypotheses and change are checked against the logs and earlier episodes before use.
Answer with ONE JSON object and nothing else:
{{"diagnosis": "...", "cause": "setting" | "hardware" | "placement_or_operator" | "unknown",
  "hypotheses": [{{"cause": "<vocabulary>", "explains": ["<symptom>", ...]}}],
  "change": {{"<setting>": <new value>}}, "expected_effect": "...", "lesson": "<one sentence to remember, or empty>"}}"""
    c = anthropic.Anthropic()
    msg = c.messages.create(model=MODEL, max_tokens=4000, messages=[{'role': 'user', 'content': prompt}])
    text = ''.join(b.text for b in msg.content if getattr(b, 'type', '') == 'text')
    m = re.search(r'\{.*\}', text, re.S)
    ans = json.loads(m.group(0)) if m else {'diagnosis': text, 'cause': 'unknown', 'change': {}}
    return ans, {'prompt_chars': len(prompt), 'in': msg.usage.input_tokens, 'out': msg.usage.output_tokens}


# ---------------- the θ gate ----------------

def gate(old, new):
    """Same idea as the program gate: a proposal is adopted only if it passes checks that do not need the real robot.
    1 bounds  2 geometry: no radius that had a grasp pose / inner-edge handling loses it
    3 replay: on every archived wrist frame of a SUCCESSFUL episode, no blob that was detected disappears or changes color"""
    reasons = TH.check_bounds({k: v for k, v in new.items()})
    if reasons:
        return False, reasons, {}
    L.load_geo()
    TH.OVERRIDE.clear(); TH.OVERRIDE.update(old)
    g_old = [r for r in range(130, 236) if L.grasp_poses(r / 1000)[1]]
    TH.OVERRIDE.clear(); TH.OVERRIDE.update(new)
    g_new = [r for r in range(130, 236) if L.grasp_poses(r / 1000)[1]]
    lost = sorted(set(g_old) - set(g_new))
    if lost:
        reasons.append('grasp pose lost at %s mm' % lost)
    if old['inner_clamp_cm'] > 0 and new['inner_clamp_cm'] == 0:
        reasons.append('inner-edge clamp switched off: cubes estimated closer than 13.8 cm would be given up again')
    ok_eps = {e['ep'] for e in episodes() if e['success']}
    lost_det, gained, n = [], 0, 0
    for ep in sorted(ok_eps):
        d = os.path.join(L.ARCHIVE, ep)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith('.ppm'):
                continue
            W, H, px = L.read_ppm(os.path.join(d, fn)); n += 1
            for col in ('green', 'blue'):
                TH.OVERRIDE.clear(); TH.OVERRIDE.update(old); a = L.blob(px, W, H, True, col)
                TH.OVERRIDE.clear(); TH.OVERRIDE.update(new); b = L.blob(px, W, H, True, col)
                if a and not b:
                    lost_det.append('%s/%s %s' % (ep, fn, col))
                elif b and not a:
                    gained += 1
    TH.OVERRIDE.clear()
    if lost_det:
        reasons.append('replay: %d detections in successful episodes would be lost (%s)' % (len(lost_det), ', '.join(lost_det[:3])))
    return not reasons, reasons, {'frames': n, 'gained_detections': gained, 'grasp_radii_lost': lost}


def advise(ep):
    e = [x for x in episodes() if x['ep'] == ep][-1]
    if e['mode'] != 'learn':
        raise SystemExit('%s is a %s episode: no advice (θ stays frozen)' % (ep, e['mode']))
    if e['success'] is None:
        raise SystemExit('record the visual check first: seen %s ok|ng' % ep)
    st = state()
    state_before = json.loads(json.dumps(st))
    fx = logic_facts(e, st)
    ans, use = ask_advisor(e, st, fx=fx)
    rec = {'ep': ep, 't': time.strftime('%Y-%m-%dT%H:%M:%S'), 'model': MODEL, 'answer': ans, 'usage': use, 'tries': [],
           'facts': fx}
    change = {k: v for k, v in (ans.get('change') or {}).items()}
    if change:                                             # LLM alone (no logic check): what the θ gate would have done
        new = dict(st['theta']); new.update(change)
        ok0, r0, i0 = gate(st['theta'], new)
        rec['llm_only'] = {'change': change, 'pass': ok0, 'reasons': r0, 'info': i0}
    cur = ans
    for attempt in (1, 2):
        lg = AB.check(fx, cur)                             # the advisor's reasoning, checked by abduction (rules.pl)
        print('logic %s %s  (logic alone: %s)' % ('PASS' if lg['pass'] else 'REJECT', lg['problems'], lg['explanations']))
        if not change:
            rec['tries'].append({'change': {}, 'logic': lg, 'gate': 'no change proposed'}); break
        new = dict(st['theta']); new.update(change)
        if lg['pass']:
            ok, reasons, info = gate(st['theta'], new)
            print('proposal %s -> gate %s %s %s' % (change, 'PASS' if ok else 'REJECT', reasons, info))
        else:
            ok, reasons, info = False, ['logic: ' + p for p in lg['problems']], {}
        rec['tries'].append({'change': change, 'pass': ok, 'reasons': reasons, 'info': info, 'logic': lg})
        if ok:
            st['adopted'].append({'ep': ep, 'change': change, 'why': cur.get('diagnosis', ''), 'gate': info,
                                  'hypotheses': cur.get('hypotheses')})
            st['theta'] = new
            break
        if attempt == 1:                                   # one revision with the logic's or the gate's reasons
            ans2, use2 = ask_advisor(e, st, fx=fx, extra='\n## Your previous proposal was REJECTED\n'
                                     + json.dumps({'hypotheses': cur.get('hypotheses'), 'change': change})
                                     + '\nReasons: ' + '; '.join(reasons) + '\nPropose again (or no change).\n')
            rec['revision'] = {'answer': ans2, 'usage': use2}
            cur = ans2
            change = dict(ans2.get('change') or {})
    try:                                                   # same episode, logs without the added hints: recorded, never adopted
        fx_p = logic_facts(e, state_before, hints=False)
        ans_p, use_p = ask_advisor(e, state_before, hints=False, fx=fx_p)
        rec['plain'] = {'answer': ans_p, 'usage': use_p, 'logic': AB.check(fx_p, ans_p)}
    except Exception as ex:
        rec['plain'] = {'error': str(ex)}
    if ans.get('lesson'):
        st['lessons'].append('%s: %s' % (ep, ans['lesson']))
    save_state(st)
    with open(ADVICE, 'a') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print(json.dumps(ans, ensure_ascii=False, indent=1))
    print('θ now:', st['theta'])


def status():
    st = state(); done = {e['ep']: e for e in episodes()}
    for ep, mode, c, p in SCHED:
        e = done.get(ep)
        print('%s %-5s %-5s %s  %s' % (ep, mode, c, p, '-' if not e else ('ok' if e['success'] else ('ng' if e['success'] is False else 'ran'))))
    print('θ in force:', st['theta']); print('adopted:', [(a['ep'], a['change']) for a in st['adopted']])


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'point': point(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 1)
    elif cmd == 'run': run(sys.argv[2])
    elif cmd == 'seen': seen(sys.argv[2], sys.argv[3], ' '.join(sys.argv[4:]))
    elif cmd == 'advise': advise(sys.argv[2])
    elif cmd == 'status': status()
