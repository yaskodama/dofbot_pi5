# test_abduce.py — the logic check on hand-made episodes (each case states what the theory must say)
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import abduce as A

TH0 = {'blue_v_min': 0.2, 'tilt_step_deg': 5, 'inner_clamp_cm': 0.0, 'min_blob_frac': 0.015,
       'green_s_min': 0.45, 'refine_gain': 0.6, 'refine_rounds': 7, 'survey_inner_cm': 13.5}
REAL_NONE = '== migrate -> Xinu on the DOFBOT Pi 5\n[1] line 62  eye.locate(real 30 any) = none\n[2] line 70  no cube in reach after 3 sweeps\ndone: placed 0'
REAL_EMPTY = ('== migrate -> Xinu on the DOFBOT Pi 5\n[1] line 62  eye.locate(real 30 any) = blue\n[8] line 110  eye.held(real) = no\n'
              'the fingers closed on nothing - look again\n[1] line 62  eye.locate(real 30 any) = none\ndone: placed 0')
CS_BLUE = ('  locate(real) survey 16 cm base 77: blue-hued px below the value floor: 412 (value 0.10-0.19)\n'
           '  locate(real) survey 21 cm base 77: nothing\n  locate(real) survey: no blue cube in reach\n')
CS_INNER = ('  locate(real) survey 16 cm base 77: green(3000 px at 15.2cm)\n'
            '  locate(real) round 1: (0.136, 0.010) r=13.6 cm is out of reach: no camera look pose (grasp pose there: yes)\n')
CS_TILT = '  locate(real) cube at (0.142, 0.000) r=14.2 cm cannot be grasped: no grasp pose with hand tilt 180..130 deg in 5 deg steps\n'
EP = lambda c, r, b, ok, **k: dict(dict(ep='A06', color=c, r_cm=r, base=b, success=ok, real_placed=0, board_stopped=False), **k)
H_OK = [dict(ep='A01', color='blue', r_cm=15, base=70, success=True, theta=TH0)]
grasp = lambda r, s: s <= 2          # geometry stub: at 14.2 cm only steps 1-2 find a pose


def case(name, e, real, cs, ans, expect_pass, hist=(), must=(), signs=None):
    fx = A.extract(e, real, cs, TH0, list(hist), grasp_ok=grasp, past_signs=signs)
    v = A.check(fx, ans)
    ok = v['pass'] == expect_pass and all(any(m in p for p in v['problems']) for m in must)
    print('%-4s %-44s pass=%-5s sym=%s\n     problems=%s\n     logic-only=%s' % (
        'ok' if ok else 'FAIL', name, v['pass'], v['symptoms'], v['problems'], v['explanations']))
    return ok


R = []
B = lambda *h: [{'cause': c, 'explains': x} for c, x in h]
R.append(case('blue unseen, floor lowered below 0.19', EP('blue', 15, 70, False), REAL_NONE, CS_BLUE,
              {'hypotheses': B(('blue_floor_too_high', ['not_seen'])), 'change': {'blue_v_min': 0.09}}, True))
R.append(case('blue unseen, floor lowered too little (0.19)', EP('blue', 15, 70, False), REAL_NONE, CS_BLUE,
              {'hypotheses': B(('blue_floor_too_high', ['not_seen'])), 'change': {'blue_v_min': 0.195}}, False,
              must=['change_unsupported']))
R.append(case('blue unseen but same floor succeeded here', EP('blue', 15, 70, False), REAL_NONE, CS_BLUE,
              {'hypotheses': B(('blue_floor_too_high', ['not_seen'])), 'change': {'blue_v_min': 0.09}}, False,
              hist=H_OK, must=['refuted']))
R.append(case('blue unseen, no evidence in log', EP('blue', 15, 70, False), REAL_NONE, '',
              {'hypotheses': B(('blue_floor_too_high', ['not_seen'])), 'change': {'blue_v_min': 0.09}}, False,
              must=['explains_nothing']))
R.append(case('board stop blamed on a setting (no evidence)', EP('blue', 15, 70, False, board_stopped=True), REAL_NONE, '',
              {'hypotheses': B(('board_stop', ['board_stop']), ('blue_floor_too_high', ['not_seen'])),
               'change': {'blue_v_min': 0.09}}, False, must=['explains_nothing']))
R.append(case('board stop + green unseen, blamed green floor too', EP('green', 17, 90, False, board_stopped=True), REAL_NONE, '',
              {'hypotheses': B(('board_stop', ['board_stop', 'not_seen']), ('operator_placement', ['not_seen'])),
               'change': {}}, False, must=['redundant']))
R.append(case('board stop, no change', EP('blue', 15, 70, False, board_stopped=True), REAL_NONE, '',
              {'hypotheses': B(('board_stop', ['board_stop', 'not_seen'])), 'change': {}}, True))
R.append(case('inner edge give-up, clamp 14.1', EP('green', 14.5, 90, False), REAL_NONE, CS_INNER,
              {'hypotheses': B(('inner_edge_unclamped', ['gave_up_reach(13.6)'])), 'change': {'inner_clamp_cm': 14.1}}, True))
R.append(case('inner edge give-up, but blamed refine gain', EP('green', 14.5, 90, False), REAL_NONE, CS_INNER,
              {'hypotheses': B(('refine_overshoot', ['gave_up_reach(13.6)'])), 'change': {'refine_gain': 0.4}}, False,
              must=['explains_nothing']))
R.append(case('no grasp at 14.2, step 5 -> 1', EP('green', 14.5, 90, False), REAL_NONE, CS_TILT,
              {'hypotheses': B(('tilt_step_too_coarse', ['no_grasp(14.2)'])), 'change': {'tilt_step_deg': 1}}, True))
R.append(case('no grasp at 14.2, step 5 -> 4 (still misses)', EP('green', 14.5, 90, False), REAL_NONE, CS_TILT,
              {'hypotheses': B(('tilt_step_too_coarse', ['no_grasp(14.2)'])), 'change': {'tilt_step_deg': 4}}, False,
              must=['change_unsupported']))
R.append(case('empty grip, blamed blue floor', EP('blue', 15, 70, False), REAL_EMPTY, CS_BLUE,
              {'hypotheses': B(('blue_floor_too_high', ['empty_grip'])), 'change': {'blue_v_min': 0.09}}, False,
              must=['unsupported_claim']))
R.append(case('success with blue risk, floor lowered', EP('blue', 17, 55, True), REAL_EMPTY, CS_BLUE,
              {'hypotheses': B(('blue_floor_too_high', ['risk(blue_floor)'])), 'change': {'blue_v_min': 0.09}}, True))
R.append(case('made-up cause', EP('blue', 15, 70, False), REAL_NONE, CS_BLUE,
              {'hypotheses': B(('lighting_changed', ['not_seen'])), 'change': {'blue_v_min': 0.09}}, False,
              must=['not_a_cause']))
# addendum c (2026-10-30): seen but discarded as closer than the survey limit (A02/A07: H3 = 14.5 cm, base 90)
CS_DROP = ('  locate(real) survey 16 cm base 77: nothing\n'
           '  locate(real) glimpse: green at 13.0 cm, base 84 — go back and look\n'
           '  locate(real) glimpse dropped: green at 13.1 cm is inside the survey limit 13.5 cm\n')
CS_OLD = ('  locate(real) glimpse: green at 13.0 cm, base 84 — go back and look\n'
          '  locate(real) survey result: [] (glimpses 2)\n')       # the A07 log, before the drop line existed
R.append(case('dropped inside the survey limit, limit 13.5 -> 13.0', EP('green', 14.5, 90, False), REAL_NONE, CS_DROP,
              {'hypotheses': B(('survey_inner_too_far', ['not_seen'])), 'change': {'survey_inner_cm': 13.0}}, True))
R.append(case('dropped inside, limit lowered too little (13.2)', EP('green', 14.5, 90, False), REAL_NONE, CS_DROP,
              {'hypotheses': B(('survey_inner_too_far', ['not_seen'])), 'change': {'survey_inner_cm': 13.2}}, False,
              must=['change_unsupported']))
R.append(case('dropped inside, but blamed the inner clamp (A07)', EP('green', 14.5, 90, False), REAL_NONE, CS_DROP,
              {'hypotheses': B(('inner_edge_unclamped', ['not_seen'])), 'change': {'inner_clamp_cm': 14.0}}, False,
              must=['explains_nothing']))
R.append(case('old log: glimpse inside the limit, not confirmed', EP('green', 14.5, 90, False), REAL_NONE, CS_OLD,
              {'hypotheses': B(('survey_inner_too_far', ['not_seen'])), 'change': {'survey_inner_cm': 12.9}}, True))
R.append(case('green unseen, no sighting at all', EP('green', 14.5, 90, False), REAL_NONE, '',
              {'hypotheses': B(('survey_inner_too_far', ['not_seen'])), 'change': {'survey_inner_cm': 12.5}}, False,
              must=['explains_nothing']))
# addendum d (2026-10-30): an earlier success refutes a cause only if it did not show that cause's sign (A03 vs A08, H2)
H_H2 = [dict(ep='A03', color='blue', r_cm=15, base=110, success=True, theta=TH0)]
CS_GAVE = '  locate(real) round 0: (0.122, -0.059) r=13.6 cm is out of reach: no camera look pose (grasp pose there: yes)\n'
ANS_CL = {'hypotheses': B(('inner_edge_unclamped', ['gave_up_reach(13.6)'])), 'change': {'inner_clamp_cm': 14.5}}
R.append(case('give-up; same spot succeeded cleanly -> refuted', EP('blue', 15, 110, False), REAL_NONE, CS_GAVE, ANS_CL, False,
              hist=H_H2, signs={'A03': []}, must=['refuted']))
R.append(case('give-up; same spot succeeded after a give-up (A03) -> not refuted', EP('blue', 15, 110, False), REAL_NONE, CS_GAVE,
              ANS_CL, True, hist=H_H2, signs={'A03': ['gave_up_reach(13.7)']}))
R.append(case('give-up; earlier success showed another sign only -> refuted', EP('blue', 15, 110, False), REAL_NONE, CS_GAVE,
              ANS_CL, False, hist=H_H2, signs={'A03': ['empty_grip']}, must=['refuted']))
fx = A.extract(EP('blue', 15, 110, True), REAL_EMPTY, CS_GAVE, TH0, [])
ok = set(fx['signs']) == {'gave_up_reach(13.6)', 'empty_grip'} and fx['symptoms'] == []
print('%-4s %-44s signs=%s sym=%s' % ('ok' if ok else 'FAIL', 'signs of a success (symptoms stay empty)', fx['signs'], fx['symptoms']))
R.append(ok)
print('%d/%d cases as expected' % (sum(R), len(R)))
sys.exit(0 if all(R) else 1)
