% rules.pl — the background theory for checking the advisor's reasoning (L1, protocol addendum 2026-10-28b).
%
% Model-based diagnosis by abduction (Reiter 1987; Kakas, Kowalski & Toni 1992): a hypothesis set H is an acceptable
% explanation of an episode iff, with this theory and the facts extracted from the logs,
%   (1) every hypothesis explains some observed symptom, and every symptom the advisor says it explains,
%   (2) H is consistent with earlier successes (no setting blamed at a value that already succeeded on the same case),
%   (3) H covers every failure symptom, and (4) H is minimal (no member is redundant).
% A setting change is adopted only if (5) an accepted hypothesis names that setting, the change goes in the direction
% the hypothesis implies, and the new value would remove the observed cause (e.g. it recovers the rejected blue pixels).
%
% Facts (written by abduce.py from the logs):  color/1, at/2 (cm, deg), setting/2, sym/1, ev/1,
%   past/5 (Ep, ok|ng, Color, Rcm, Base), past_setting/3, past_sign/2 (what an earlier episode's logs show); the advisor's answer: hyp/1, claims/2, change/2.
:- discontiguous explains/2.
:- dynamic est/2, clamped/1.
:- dynamic color/1, at/2, setting/2, sym/1, ev/1, past/5, past_setting/3, past_sign/2, hyp/1, claims/2, change/2.

% ---- the vocabulary of causes ----
% setting causes: Cause, the setting it blames, the direction a fix must take
setting_cause(blue_floor_too_high,      blue_v_min,     down).
setting_cause(green_sat_floor_too_high, green_s_min,    down).
setting_cause(blob_size_floor_too_high, min_blob_frac,  down).
setting_cause(inner_edge_unclamped,     inner_clamp_cm, up).
setting_cause(survey_inner_too_far,     survey_inner_cm, down).   % addendum c (2026-10-30)
setting_cause(tilt_step_too_coarse,     tilt_step_deg,  down).
setting_cause(refine_too_weak,          refine_gain,    up).
setting_cause(refine_too_weak,          refine_rounds,  up).
setting_cause(refine_overshoot,         refine_gain,    down).
setting_cause(inner_angle_unrefined,    inner_refine_angle, up).   % C-1 (2026-11-01)
setting_cause(inner_radius_underread,   inner_r_bias_cm,    up).   % C-1 (2026-11-01)
setting_cause(inner_out_of_view,        survey_inner_ring_cm, up). % C-4 (2026-11-03)
other_cause(board_stop).            % the arm's servo board stopped (hardware)
other_cause(grip_miss).             % the fingers closed beside the cube (physical: slip, push, offset)
other_cause(operator_placement).    % the cube was not where the schedule says, or the verdict disagrees with the logs
other_cause(unknown).
cause(C) :- setting_cause(C, _, _) ; other_cause(C).
color_specific(blue_floor_too_high). color_specific(green_sat_floor_too_high). color_specific(blob_size_floor_too_high).

required(S) :- sym(S), S \= risk(_).          % failure symptoms must be explained; risk(_) may be

% ---- what explains what (each rule needs the evidence the cause would leave in the logs) ----
explains(blue_floor_too_high, not_seen) :-
    color(blue), sym(not_seen), ev(blue_below_floor(N, _, _)), N >= 20.
explains(blue_floor_too_high, risk(blue_floor)) :- sym(risk(blue_floor)).
explains(inner_edge_unclamped, gave_up_reach(R)) :-
    sym(gave_up_reach(R)), ev(grasp_pose_at(R)), setting(inner_clamp_cm, Cl), (Cl =:= 0 ; R >= Cl).
explains(survey_inner_too_far, not_seen) :-                     % seen, but discarded as closer than the survey limit
    sym(not_seen), ev(dropped_inside(R)), setting(survey_inner_cm, Lim), R < Lim.
explains(tilt_step_too_coarse, no_grasp(R)) :-
    sym(no_grasp(R)), setting(tilt_step_deg, S), ev(grasp_ok(R, S2)), S2 < S.
explains(refine_too_weak, empty_grip) :- sym(empty_grip), ev(refine_unconverged(_)).
explains(refine_overshoot, empty_grip) :- sym(empty_grip), ev(refine_unconverged(_)).
% C-1 (2026-11-01): the estimate is compared with the scheduled place at/2 (the operator puts the cube there)
explains(inner_angle_unrefined, empty_grip) :-                  % clamped, so the survey's base angle was never corrected
    sym(empty_grip), ev(clamped(_)), at(_, B0), ev(est(_, B)), abs(B - B0) >= 5,
    setting(inner_refine_angle, N), N < 3.
explains(inner_radius_underread, not_seen) :-                   % discarded inside the limit, and read short
    sym(not_seen), ev(dropped_inside(R)), setting(survey_inner_cm, Lim), R < Lim, at(R0, _), R0 - R >= 0.5.
explains(inner_radius_underread, gave_up_reach(R)) :-
    sym(gave_up_reach(R)), at(R0, _), R0 - R >= 0.5.
% C-4 (2026-11-03): the cube lies at the inner edge, no look of the 16 cm row saw it (only glimpses while moving), and there is no inner row
explains(inner_out_of_view, not_seen) :-
    sym(not_seen), ev(survey_row_missed(_)), setting(survey_inner_ring_cm, Rg), Rg =:= 0.
explains(board_stop, S) :- sym(board_stop), sym(S), S \= risk(_).
explains(grip_miss, empty_grip) :- sym(empty_grip).
explains(operator_placement, S) :- sym(S), memberchk(S, [not_seen, wrong_zone, failed_visual, empty_grip]).
explains(unknown, failed_visual) :- sym(failed_visual).

% ---- consistency with earlier successes ----
% blaming setting K for this case is refuted if an earlier episode on the same case (same place, and same color for
% color settings) succeeded with K at exactly the value in force now
% ... unless that success itself shows the sign this cause leaves (addendum d, 2026-10-30: A03 gave up at 13.7 cm in its
% first sweep and succeeded only because the next sweep estimated 13.8 cm — a lucky success is no evidence against the cause)
refuted(C, Ep) :-
    setting_cause(C, K, _), setting(K, V), at(R0, B0),
    past(Ep, ok, Col, R, B), past_setting(Ep, K, V),
    abs(R - R0) =< 1.0, abs(B - B0) =< 10,
    ( color_specific(C) -> color(Col) ; true ),
    \+ ( sign_of(C, S), past_sign(Ep, S) ),
    \+ mixed(C, K, V).
% addendum (2026-11-04, D_v1 before freezing): a success is no evidence against C where the same setting value has also
% failed with C's sign at the same place (and color, for color settings): the outcome there is mixed, not settled.
% C19: C03, C04, C07, C08, C15, C16 succeeded without the inner row, but C12 at the same place missed it with that setting.
mixed(C, K, V) :-
    at(R0, B0), sign_of(C, S),
    past(Ep2, ng, Col2, R2, B2), past_setting(Ep2, K, V), past_sign(Ep2, S),
    abs(R2 - R0) =< 1.0, abs(B2 - B0) =< 10,
    ( color_specific(C) -> color(Col2) ; true ).
sign_of(inner_edge_unclamped, gave_up_reach(_)).
sign_of(tilt_step_too_coarse, no_grasp(_)).
sign_of(refine_too_weak, empty_grip).
sign_of(refine_overshoot, empty_grip).
sign_of(survey_inner_too_far, dropped_inside(_)).
sign_of(blue_floor_too_high, blue_below_floor(_, _, _)).
sign_of(inner_angle_unrefined, clamped(_)).
sign_of(inner_radius_underread, dropped_inside(_)).
sign_of(inner_radius_underread, gave_up_reach(_)).
sign_of(inner_out_of_view, survey_row_missed(_)).

valid(C) :- hyp(C), \+ refuted(C, _), explains(C, _).

% ---- checks on the advisor's hypothesis set ----
problem(not_a_cause(C))         :- hyp(C), \+ cause(C).
problem(refuted(C, Ep))         :- hyp(C), refuted(C, Ep).
problem(explains_nothing(C))    :- hyp(C), cause(C), \+ refuted(C, _), \+ explains(C, _).
problem(unsupported_claim(C,S)) :- claims(C, S), hyp(C), \+ explains(C, S).
problem(uncovered(S))           :- required(S), \+ (valid(C), explains(C, S)).
problem(redundant(C))           :- valid(C), \+ (explains(C, S), \+ (valid(C2), C2 \== C, explains(C2, S))).
problem(change_unsupported(K, V)) :- change(K, V), \+ supported(K, V).

supported(K, New) :-
    valid(C), setting_cause(C, K, Dir), setting(K, Cur), dir_ok(Dir, Cur, New), effective(C, K, New).
dir_ok(down, Cur, New) :- New < Cur.
dir_ok(up,   Cur, New) :- New > Cur.
effective(blue_floor_too_high, blue_v_min, New) :- !,       % must let at least the brightest rejected blue pixels in
    ev(blue_below_floor(_, _, Vhi)), New < Vhi.
effective(inner_edge_unclamped, inner_clamp_cm, New) :- !,  % the clamp must reach every radius where it gave up
    forall(sym(gave_up_reach(R)), New > R).
effective(survey_inner_too_far, survey_inner_cm, New) :- !,  % the new limit must keep at least one discarded sighting
    ev(dropped_inside(R)), New =< R.
effective(tilt_step_too_coarse, tilt_step_deg, New) :- !,   % the new step must find a grasp pose where none was found
    forall(sym(no_grasp(R)), ev(grasp_ok(R, New))).
effective(inner_angle_unrefined, inner_refine_angle, New) :- !, New >= 1.
effective(inner_radius_underread, inner_r_bias_cm, New) :- !,   % must reach the limit / a look pose, must not overshoot the truth
    forall(sym(gave_up_reach(R)), R + New >= 13.8),
    ( sym(not_seen) -> once((ev(dropped_inside(R)), setting(survey_inner_cm, Lim), R + New >= Lim)) ; true ),
    at(R0, _),
    \+ ( ev(est(R1, _)), R1 + New > R0 + 1.0 ),
    \+ ( ev(dropped_inside(R2)), R2 + New > R0 + 1.0 ),
    \+ ( sym(gave_up_reach(R3)), R3 + New > R0 + 1.0 ).
effective(inner_out_of_view, survey_inner_ring_cm, New) :- !,   % a look pose exists, and the row is not beyond the cube
    New >= 13.8, at(R0, _), New =< R0.
effective(_, _, _).

% ---- abduction without the LLM: every minimal acceptable explanation (up to 2 causes) ----
candidate(C) :- cause(C), \+ refuted(C, _), explains(C, _).
covers(H) :- forall(required(S), (member(C, H), explains(C, S))).
nonredundant(H) :- forall(member(C, H), (explains(C, S), \+ (member(C2, H), C2 \== C, explains(C2, S)))).
explanation(H) :-
    findall(C, candidate(C), Cs0), sort(Cs0, Cs),
    ( H = [] ; H = [_] ; H = [_, _] ),
    subset_of(H, Cs), covers(H), nonredundant(H),
    ( H = [] -> \+ required(_) ; true ).
subset_of([], _).
subset_of([X|Xs], [X|Ys]) :- subset_of(Xs, Ys).
subset_of(Xs, [_|Ys]) :- subset_of(Xs, Ys).
minimal_explanation(H) :- explanation(H), \+ (explanation(H2), H2 \== H, subset_of(H2, H)).

report :-
    forall(problem(P), (print(problem(P)), nl)),
    forall(minimal_explanation(H), (print(explanation(H)), nl)),
    forall((cause(C), refuted(C, Ep)), (print(refutes(Ep, C)), nl)).
