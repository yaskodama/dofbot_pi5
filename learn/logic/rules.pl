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
%   past/5 (Ep, ok|ng, Color, Rcm, Base), past_setting/3; the advisor's answer: hyp/1, claims/2, change/2.
:- discontiguous explains/2.
:- dynamic color/1, at/2, setting/2, sym/1, ev/1, past/5, past_setting/3, hyp/1, claims/2, change/2.

% ---- the vocabulary of causes ----
% setting causes: Cause, the setting it blames, the direction a fix must take
setting_cause(blue_floor_too_high,      blue_v_min,     down).
setting_cause(green_sat_floor_too_high, green_s_min,    down).
setting_cause(blob_size_floor_too_high, min_blob_frac,  down).
setting_cause(inner_edge_unclamped,     inner_clamp_cm, up).
setting_cause(tilt_step_too_coarse,     tilt_step_deg,  down).
setting_cause(refine_too_weak,          refine_gain,    up).
setting_cause(refine_too_weak,          refine_rounds,  up).
setting_cause(refine_overshoot,         refine_gain,    down).
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
explains(tilt_step_too_coarse, no_grasp(R)) :-
    sym(no_grasp(R)), setting(tilt_step_deg, S), ev(grasp_ok(R, S2)), S2 < S.
explains(refine_too_weak, empty_grip) :- sym(empty_grip), ev(refine_unconverged(_)).
explains(refine_overshoot, empty_grip) :- sym(empty_grip), ev(refine_unconverged(_)).
explains(board_stop, S) :- sym(board_stop), sym(S), S \= risk(_).
explains(grip_miss, empty_grip) :- sym(empty_grip).
explains(operator_placement, S) :- sym(S), memberchk(S, [not_seen, wrong_zone, failed_visual, empty_grip]).
explains(unknown, failed_visual) :- sym(failed_visual).

% ---- consistency with earlier successes ----
% blaming setting K for this case is refuted if an earlier episode on the same case (same place, and same color for
% color settings) succeeded with K at exactly the value in force now
refuted(C, Ep) :-
    setting_cause(C, K, _), setting(K, V), at(R0, B0),
    past(Ep, ok, Col, R, B), past_setting(Ep, K, V),
    abs(R - R0) =< 1.0, abs(B - B0) =< 10,
    ( color_specific(C) -> color(Col) ; true ).

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
effective(tilt_step_too_coarse, tilt_step_deg, New) :- !,   % the new step must find a grasp pose where none was found
    forall(sym(no_grasp(R)), ev(grasp_ok(R, New))).
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
