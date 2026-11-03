#!/usr/bin/env python3
# cf_replay.py — per-trial counterfactual (post hoc, 2026-11-04): would θ* (C-3) get past the point where each failed real trial stopped?
#   1 frames: the archived REAL survey sweeps of the trial, fed in order to locate.survey() under the trial's own θ and under θ*
#     (the 14 cm row of θ* has no archived frame; the glimpses taken while moving were not archived)
#   2 log: the go-back estimates in the color-service log ("glimpse confirmed/dropped: <col> at R cm"), re-biased to θ* and judged
#     against θ*'s survey limit, look pose and clamp
#   3 geometry: whether θ* has a grasp pose at the final radius
# Never moves the arm. Output: ~/paper1_sim2real/data/cf/cf_replay.jsonl
#   python3 learn/cf_replay.py          θ* (C-3)
#   python3 learn/cf_replay.py human    the human fixes of E0' only (θ0 + blue 0.06, clamp 14.1, tilt 1; as in E0m) -> cf_human.jsonl
import sys, os, json, math, re, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.dirname(HERE))
import locate as L, theta as TH
import c3_run
L.load_geo(); L.archive = lambda *a, **k: None
STAR = dict(c3_run.THETA_STAR)
TH0 = {k: v[1] for k, v in TH.SCHEMA.items()}
D = os.path.expanduser('~/paper1_sim2real/data')
CSLOG = os.path.join(os.path.dirname(HERE), 'color_service.log')
OUT = os.path.join(D, 'cf', 'cf_replay.jsonl')
HUMAN = dict(TH0, blue_v_min=0.06, inner_clamp_cm=14.1, tilt_step_deg=1)
DEVICE = {'A10', 'B01', 'C06', 'C12', 'C13', 'C17'}        # board stop / board 'err': not a θ question
GRIP = {'B02', 'B07'}                                      # failed at the grip, after the cube was found


def episodes():
    eps = []
    for ds in ('learn', 'c2', 'c3'):
        eps += [dict(json.loads(x), ds=ds) for x in open(os.path.join(D, ds, 'episodes.jsonl'))]
    return eps


def real_sweeps(e):
    log = open(os.path.join(D, e['ds'], 'logs', e['log'])).read()
    m = re.search(r'^(\d\d:\d\d:\d\d) == migrate -> Xinu on the DOFBOT', log, re.M)
    t0 = datetime.datetime.fromisoformat(e['t_start'][:10] + 'T' + m.group(1)).timestamp()
    d = os.path.join(L.ARCHIVE, e['ep']); sw, cur = [], []
    for fn in sorted(os.listdir(d)):
        if not fn.endswith('.json'):
            continue
        j = json.load(open(os.path.join(d, fn)))
        if j['t'] < t0:
            continue                                  # the simulator's frames come first
        if j['what'] == 'survey':
            cur.append(fn[:-5])
            if len(cur) == 8: sw.append(cur); cur = []
        elif cur:
            sw.append(cur); cur = []
    return [s for s in sw + [cur] if len(s) == 8]


def survey(e, names, th):
    TH.OVERRIDE.clear(); TH.OVERRIDE.update(th)
    it, row = iter(names), [None]
    orig = L.poses
    def poses(r):
        row[0] = round(r, 2); return orig(r)
    def shoot():                                       # the 16 and 21 cm rows have frames; θ*'s 14 cm row has none
        return L.read_ppm(os.path.join(L.ARCHIVE, e['ep'], next(it) + '.ppm')) if row[0] in (0.16, 0.21) else None
    L.poses = poses
    try:
        found = L.survey(lambda s1, look: None, shoot, False, lambda s: None, None, e['color'])   # Xinu UVC frames are not rotated
    finally:
        L.poses = orig; TH.OVERRIDE.clear()
    f = [d for d in found if d['color'] == e['color']]
    return round(math.hypot(f[0]['x'], f[0]['z']) * 100, 1) if f else None


def rebias(r_cm, th_from, th_to):
    """an estimate logged under th_from's inner_r_bias_cm -> the same camera reading under th_to's"""
    TH.OVERRIDE.clear(); TH.OVERRIDE.update(th_from)
    lo, hi = 0.05, r_cm / 100
    for _ in range(60):                                # invert debias (monotone in r)
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if math.hypot(*L.debias(mid, 0.0)) < r_cm / 100 else (lo, mid)
    TH.OVERRIDE.clear(); TH.OVERRIDE.update(th_to)
    r = math.hypot(*L.debias(lo, 0.0)); TH.OVERRIDE.clear()
    return round(r * 100, 1)


def star_path(r_cm):
    """θ*: accept? look pose or clamp? grasp pose at the final radius?"""
    TH.OVERRIDE.clear(); TH.OVERRIDE.update(STAR)
    r = r_cm / 100
    if not (L.reach_lo() <= r <= L.REACH[1]):
        TH.OVERRIDE.clear(); return 'inside the survey limit'
    how = 'look pose'
    if not L.poses(r)[0]:
        clamp = TH.get('inner_clamp_cm') / 100
        if not (clamp > 0 and r < clamp):
            TH.OVERRIDE.clear(); return 'no look pose'
        n = TH.get('inner_refine_angle')
        r, how = clamp, 'clamp %.1f + %s' % (clamp * 100, 'angle refine' if n else 'stop refining')
    ok = bool(L.grasp_poses(r)[1]); TH.OVERRIDE.clear()
    return how + (', grasp pose' if ok else ', NO grasp pose')


def cs_lines(e):
    a, b = e['cslog']
    with open(CSLOG, 'rb') as f:
        f.seek(a); t = f.read(b - a).decode('utf-8', 'ignore')
    return [l.strip() for l in t.splitlines() if 'locate(real)' in l]


def main():
    global STAR, OUT
    if sys.argv[1:] == ['human']:
        STAR, OUT = HUMAN, os.path.join(D, 'cf', 'cf_human.jsonl')
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    rows = []
    for e in episodes():
        if e['success'] is not False:
            continue
        th = dict(TH0, **(e.get('theta') or {}))
        sw = real_sweeps(e)
        rec = {'ep': e['ep'], 'color': e['color'], 'pos': e['pos'], 'board_stopped': e['board_stopped'], 'visual': e['visual'],
               'frames_orig': [survey(e, s, th) for s in sw], 'frames_star': [survey(e, s, STAR) for s in sw]}
        rec['frames_star_path'] = [star_path(r) if r else None for r in rec['frames_star']]
        gl = []
        for l in cs_lines(e):
            m = re.search(r'glimpse (confirmed|dropped): (\w+) at ([\d.]+) cm', l)
            if m and m.group(2) == e['color']:
                rs = rebias(float(m.group(3)), th, STAR)
                gl.append({'logged': float(m.group(3)), 'star': rs, 'path': star_path(rs)})
        rec['goback_log'] = gl
        rec['glimpse_log'] = [float(m.group(1)) for l in cs_lines(e)       # seen while moving (no frame archived); θ* would go back from >= 14 cm
                              for m in [re.search(r'glimpse: %s at ([\d.]+) cm' % e['color'], l)] if m]
        paths = [p for p in rec['frames_star_path'] if p] + [g['path'] for g in gl]
        rec['passes_find'] = any(p.endswith(', grasp pose') for p in paths)
        rec['verdict'] = ('device' if e['ep'] in DEVICE else
                          ('grip: found, grip not replayable' if rec['passes_find'] and (STAR['inner_refine_angle'] or e['ep'] == 'B02')
                           else 'grip: found, same no-refine grip as the failure' if rec['passes_find'] else 'does not pass') if e['ep'] in GRIP else
                          'passes' if rec['passes_find'] else
                          'undetermined: glimpse only, no frame from the go-back view' if rec['glimpse_log'] and STAR['survey_inner_ring_cm'] > 0 else
                          'does not pass')
        rec['goback_not_confirmed'] = sum('glimpse not confirmed' in l for l in cs_lines(e))
        rows.append(rec)
    with open(OUT, 'w') as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
    from collections import Counter
    print(Counter(r['verdict'] for r in rows))
    for r in rows:
        print(r['verdict'][:12], r['ep'], r['color'], r['pos'], 'frames', r['frames_orig'], '->', r['frames_star'], r['frames_star_path'][:1],
              '| go-back', [(g['logged'], g['star'], g['path']) for g in r['goback_log']][:3], 'not confirmed', r['goback_not_confirmed'], 'glimpses', r['glimpse_log'][:6])


if __name__ == '__main__':
    main()
