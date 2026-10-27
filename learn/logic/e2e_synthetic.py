# e2e_synthetic.py — three synthetic learn episodes through advise() (LLM + logic + θ gate). Calls the LLM. Usage: python3 learn/logic/e2e_synthetic.py <scratch dir>
import sys, os, json
sys.path.insert(0, os.path.expanduser('~/dofbot_pi5/learn'))
import run_learn as RL
D = sys.argv[1] if len(sys.argv) > 1 else '/tmp/l1logic_e2e'
os.makedirs(D + '/logs', exist_ok=True)
for f in os.listdir(D):
    if f.endswith('.json') or f.endswith('.jsonl'): os.remove(os.path.join(D, f))
RL.DATA, RL.EPS, RL.STATE, RL.ADVICE = D, D + '/episodes.jsonl', D + '/state.json', D + '/advice.jsonl'
RL.CSLOG = D + '/cs.log'
TH0 = RL.state()['theta']
HEAD = '10:00:00 == migrate -> Xinu simulator\n  [1] eye.locate(sim 30 any) = blue\n  placed 1\n== GATE: pass\n10:01:00 == migrate -> Xinu on the DOFBOT Pi 5 : POST\n'
CASES = [
 ('A06', 'blue', 15, 70, False, False, HEAD + '[1] line 62  eye.locate(real 30 any) = none\n[2] line 70  nothing found (sweep 1)\n[1] line 62  eye.locate(real 30 any) = none\n[2] line 70  no cube in reach after 3 sweeps\ndone: placed 0, 9 steps\n',
  '  locate(real) survey 16 cm base 50: nothing\n  locate(real) survey 16 cm base 77: blue-hued px below the value floor: 412 (value 0.10-0.19)\n  locate(real) survey 21 cm base 77: nothing\n  locate(real) survey result: [] (glimpses 0)\n  locate(real) survey: no blue cube in reach\n', 'ng 青は置いたままで動かず'),
 ('A07', 'green', 14.5, 90, False, True, HEAD + '[1] line 62  eye.locate(real 30 any) = green\n[2] eye.get(real base) = 90\n[6] eye.lower(real here 30) = ok 1.2\n(no answer from the arm board)\ndone: placed 0, 6 steps\n',
  '  locate(real) survey 16 cm base 77: green(3100 px at 14.9cm)\n  locate(real) round 0: base 90 look [80, 20, 10] -> green n=8000 at (80,60) -> cube (0.146, 0.001)\n', 'ng 下ろした所で腕が止まった'),
 ('A08', 'green', 14.5, 90, False, False, HEAD + '[1] line 62  eye.locate(real 30 any) = none\n[2] line 70  no cube in reach after 3 sweeps\ndone: placed 0\n',
  '  locate(real) survey 16 cm base 77: green(3000 px at 15.2cm)\n  locate(real) round 0: base 90 look [80, 20, 10] -> green n=8100 at (80,70) -> cube (0.139, 0.002)\n  locate(real) round 1: (0.136, 0.002) r=13.6 cm is out of reach: no camera look pose (grasp pose there: yes)\n', 'ng 見つけたのに掴みに行かない'),
]
for ep, c, r, b, ok, stop, real, cs, vis in CASES:
    open(D + '/logs/%s.log' % ep, 'w').write(real)
    a = os.path.getsize(RL.CSLOG) if os.path.exists(RL.CSLOG) else 0
    open(RL.CSLOG, 'a').write(cs)
    rec = {'ep': ep, 'mode': 'learn', 'color': c, 'pos': '-', 'r_cm': r, 'base': b, 'theta': RL.state()['theta'],
           'real_placed': 0, 'held_readbacks': [], 'board_stopped': stop, 'cslog': [a, os.path.getsize(RL.CSLOG)],
           'log': '%s.log' % ep, 'visual': vis, 'success': ok}
    open(RL.EPS, 'a').write(json.dumps(rec, ensure_ascii=False) + '\n')
    print('\n######', ep, c, r, b)
    RL.advise(ep)
