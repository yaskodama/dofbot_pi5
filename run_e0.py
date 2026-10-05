#!/usr/bin/env python3
# run_e0.py — run one trial of E0′ (baseline performance of the real robot) and record it. Protocol: ~/paper1_sim2real/protocol/E0prime_v1.md
#   python3 run_e0.py <trial number> <1|2> "<description of conditions>"
# 1) run sort_real.aipl once on the real robot 2) check the left/right drop-off spots with the camera 3) collect finger readback and board state, record as one JSON line
import sys, os, time, json, socket, subprocess, urllib.request, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import locate as L

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.expanduser('~/paper1_sim2real/data/e0prime/trials.jsonl')
REPL = os.path.expanduser('~/aios/abclcp')


def ask(cmd, timeout=200):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(timeout)
    rid = int(time.time() * 1000) % 1000000 + 800000
    s.sendto(('Q %d %s\n' % (rid, cmd)).encode(), ('127.0.0.1', 9012))
    try:
        while True:
            d = s.recvfrom(500)[0].decode().strip()
            if d.startswith('R %d ' % rid) or d == 'R %d' % rid:
                return d.split(' ', 2)[2] if d.count(' ') >= 2 else ''
    except socket.timeout:
        return 'timeout'


def main():
    n, kind, cond = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
    log = os.path.join(HERE, 'aipl', 'e0_trial%02d.log' % n)
    ver0 = L.arm_udp('ver', tries=3)
    t0 = time.time()
    env = dict(os.environ)
    p = subprocess.Popen(['bash', '-lc', 'cd %s && eval "$(opam env)" && ./src/abclrepl_thread -q -f %s/aipl/r_sort_real.repl' % (REPL, HERE)],
                         stdout=open(log, 'w'), stderr=subprocess.STDOUT)
    done = False
    stopped_mid = False
    next_ver = time.time() + 30
    while time.time() - t0 < 1500:
        time.sleep(2)
        if time.time() >= next_ver:          # every 30 s, check the arm board still answers; if it has stalled, abort (don't burn time spinning idle)
            next_ver = time.time() + 30
            if '0.-1' in L.arm_udp('ver', tries=2):
                stopped_mid = True
                break
        cur = open(log, errors='ignore').read()
        if '== done' in cur:
            done = True
            break
        if '[Abort]' in cur or 'Type error' in cur:     # failed while loading (the robot did not move)
            break
    p.kill(); subprocess.run(['pkill', '-f', 'abclrepl_thread.*r_sort_real.repl'])
    t1 = time.time()
    txt = open(log, errors='ignore').read()
    m = re.search(r'real arm placed (\d+) cube', txt)
    placed = int(m.group(1)) if m else None
    grasp_tries = len(re.findall(r'try \d+: (?:green|blue) cube at base', txt))
    surveys_empty = len(re.findall(r'no cube in reach', txt))
    dropped = len(re.findall(r'dropped while lifting', txt))
    held = json.loads(urllib.request.urlopen('http://localhost:8091/held?since=%f' % t0, timeout=5).read())
    if stopped_mid:
        right = left = 'skipped (board stopped)'
    else:
        right = ask('Camera check real 150')          # green drop-off spot
        left = ask('Camera check real 30')            # blue drop-off spot
        L.move(90, [90, 90, 90], 2500, 30)
    ver1 = L.arm_udp('ver', tries=3)
    rec = {'trial': n, 'kind': kind, 'cond': cond, 't_start': round(t0, 1), 'minutes': round((t1 - t0) / 60, 2),
           'finished': done, 'placed_reported': placed, 'grasp_tries': grasp_tries, 'empty_surveys': surveys_empty,
           'dropped_while_lifting': dropped, 'held_readbacks': [v for _, v in held],
           'place_right_seen': right, 'place_left_seen': left,
           'board_before': ver0, 'board_after': ver1, 'board_stopped': ('0.-1' in ver1) or ver1 == '',
           'log': os.path.basename(log), 'stopped_mid_run': stopped_mid}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, 'a') as f:
        f.write(json.dumps(rec, ensure_ascii=False) + '\n')
    print(json.dumps(rec, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
