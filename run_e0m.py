#!/usr/bin/env python3
# run_e0m.py — one trial of E0m (the mobile-agent version of E0'). Protocol: ~/paper1_sim2real/protocol/E0m_v1.md
#   python3 run_e0m.py point <trial> [k]   point the real fingertip at where cube k (1 or 2) of the trial goes
#   python3 run_e0m.py run <trial> [label] dock.py once (CG cubes at the same spots -> sim -> gate -> real), check the
#                                          drop-off spots with the camera, record one JSON line
#   python3 run_e0m.py seen <trial> <ok|ng> [note]   add the operator's visual check to the trial's record
import sys, os, time, json, re, subprocess, urllib.request
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import locate as L
from run_e0 import ask

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.expanduser('~/paper1_sim2real/data/e0m')
OUT = os.path.join(DATA, 'trials.jsonl')

P = {'P1': (17, 90), 'P2': (15, 70), 'P3': (20, 110), 'P4': (17, 55), 'P5': (20, 125)}   # (cm from base axis, base deg)
ONE = [('green', 'P1'), ('blue', 'P2'), ('green', 'P3'), ('blue', 'P4'), ('green', 'P5'),
       ('blue', 'P1'), ('green', 'P2'), ('blue', 'P3'), ('green', 'P4'), ('blue', 'P5')]
Q = {'Q1': ('P3', 'P2'), 'Q2': ('P2', 'P3'), 'Q3': ('P5', 'P4'), 'Q4': ('P4', 'P5'), 'Q5': ('P1', 'P4')}   # (green, blue)


def plan(n):
    """trial n -> list of (color, position)"""
    if 1 <= n <= 20:
        return [ONE[(n - 1) % 10]]
    if 21 <= n <= 30:
        g, b = Q['Q%d' % ((n - 21) // 2 + 1)]
        return [('green', g), ('blue', b)]
    raise SystemExit('trial number must be 1..30')


def point(n, k):
    color, pos = plan(n)[k - 1]
    r, base = P[pos]
    s = L.point_pose(r / 100.0)
    L.move(base, s, 2500, 30)
    print('trial %d: put the %s cube under the fingertip (%s: %d cm, base %d deg)' % (n, color, pos, r, base))


def cam_on():
    """-> (state right after the dock, result of the restart or '')"""
    def get(u, t):
        try:
            return L.http_get(u, t).decode('ascii', 'ignore').strip()
        except Exception as ex:
            return 'err %s' % ex
    st = get('http://192.168.3.101/cam?w=160', 8)
    if 'streaming' in st:
        return 'streaming', ''
    r = get('http://192.168.3.101/cam/start?frame=3&fps=10', 15).splitlines()[-1:] or ['']
    time.sleep(3)
    return st.split()[-1] if st else '?', r[0].strip()


def run(n, label):
    cubes = plan(n)
    at = ','.join('%s:%d:%d' % (c, P[p][0], P[p][1]) for c, p in cubes)
    which = 'both' if len(cubes) == 2 else cubes[0][0]
    cond = ' + '.join('%s %s' % (c, p) for c, p in cubes)
    os.makedirs(os.path.join(DATA, 'logs'), exist_ok=True)
    tag = label or str(n)
    log = os.path.join(DATA, 'logs', 'trial%s.log' % tag)
    summ = os.path.join(DATA, 'logs', 'trial%s.json' % tag)
    L.move(90, [90, 90, 90], 2000, 30)                     # out of the way before the agent arrives
    time.sleep(2.2)
    ver0 = L.arm_udp('ver', tries=3)
    t0 = time.time()
    with open(log, 'w') as f:
        try:
            rc = subprocess.run([sys.executable, '-u', os.path.join(HERE, 'agent', 'dock.py'), '--cubes', which,
                                 '--at', at, '--summary', summ], stdout=f, stderr=subprocess.STDOUT, timeout=1500).returncode
        except subprocess.TimeoutExpired:
            rc = 'timeout'
    t1 = time.time()
    txt = open(log, errors='ignore').read()
    try:
        s = json.load(open(summ))
    except (OSError, ValueError):
        s = {'placed': {}, 'gate': None}
    real_part = txt.split('== migrate', 1)[1] if '== migrate' in txt else ''
    held = json.loads(urllib.request.urlopen('http://localhost:8091/held?since=%f' % t0, timeout=5).read())
    ver1 = L.arm_udp('ver', tries=3)
    stopped = ('0.-1' in ver1) or ver1 == ''
    cam = ('?', '')
    if stopped:
        right = left = 'skipped (board stopped)'
    else:
        cam = cam_on()                                     # the board's camera sometimes stops by the end of a run (cause unknown)
        right = ask('Camera check real 150')               # green drop-off spot
        left = ask('Camera check real 30')                 # blue drop-off spot
        L.move(90, [90, 90, 90], 2500, 30)
    want = {c for c, _ in cubes}
    cam_ok = (('green' not in want) or right == 'green') and (('blue' not in want) or left == 'blue')
    g = s.get('gate') or {}
    rec = {'trial': n, 'label': tag, 'kind': len(cubes), 'cond': cond, 'at': at,
           't_start': time.strftime('%Y-%m-%dT%H:%M:%S', time.localtime(t0)), 'minutes': round((t1 - t0) / 60, 2),
           'dock_rc': rc, 'sim_placed': s['placed'].get('sim'), 'gate_pass': g.get('pass'), 'gate_reasons': g.get('reasons'),
           'migrated': g.get('migrated'), 'real_placed': s['placed'].get('real'),
           'resends': real_part.count('send it again'), 'grasp_tries': real_part.count('grasp ok'),
           'empty_locates': len(re.findall(r'eye\.locate\(real [^)]*\) = none', real_part)),
           'held_readbacks': [v for _, v in held], 'place_right_seen': right, 'place_left_seen': left,
           'camera_success': cam_ok, 'cam_after_dock': cam[0], 'cam_restart': cam[1], 'visual': None, 'success': None,
           'board_before': ver0, 'board_after': ver1, 'board_stopped': stopped, 'log': os.path.basename(log)}
    with open(OUT, 'a') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print(json.dumps(rec, ensure_ascii=False, indent=1))


def seen(n, verdict, note):
    """the operator's visual check decides success (the protocol: camera, but the eye wins when they disagree)"""
    rows = [json.loads(x) for x in open(OUT)]
    for r in reversed(rows):
        if r['label'] == n:
            r['visual'] = verdict + ((' ' + note) if note else '')
            r['success'] = verdict == 'ok'
            break
    else:
        raise SystemExit('no trial labelled %s' % n)
    with open(OUT, 'w') as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + '\n' for r in rows)
    print('trial %s: success=%s' % (n, verdict == 'ok'))


if __name__ == '__main__':
    cmd = sys.argv[1]
    if cmd == 'point':
        point(int(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 1)
    elif cmd == 'run':
        run(int(sys.argv[2]), sys.argv[3] if len(sys.argv) > 3 else '')
    elif cmd == 'recheck':                                 # redo the camera check of the drop-off spots for a recorded trial
        cam_on()
        r, l = ask('Camera check real 150'), ask('Camera check real 30')
        L.move(90, [90, 90, 90], 2500, 30)
        rows = [json.loads(x) for x in open(OUT)]
        for x in reversed(rows):
            if x['label'] == sys.argv[2]:
                want = set(c.split()[0] for c in x['cond'].split(' + '))
                x.update(place_right_seen=r, place_left_seen=l, recheck=time.strftime('%H:%M:%S'),
                         camera_success=(('green' not in want) or r == 'green') and (('blue' not in want) or l == 'blue'))
                break
        with open(OUT, 'w') as f:
            f.writelines(json.dumps(x, ensure_ascii=False) + '\n' for x in rows)
        print('right', r, 'left', l)
    elif cmd == 'seen':
        seen(sys.argv[2], sys.argv[3], ' '.join(sys.argv[4:]))
