% argue.pl — the advisor's reasons as checkable argument terms (prototype, 2026-11-04).
%
% rules.pl checks the advisor's hypotheses and change (abduction). This file adds the rest of "why it advised that",
% which so far was free text: the observations it relies on, the causes it rules out and why, the lessons it applies,
% how it chose the value, and what it predicts. Each is a term the logic can check against the facts from the logs.
%
% Facts beyond rules.pl (written by argue_proto.py): past_at/3 (Ep, Rcm, Base), past_ok/1, past_ev/2 (Ep, Evidence) for
% earlier episodes of any phase; past_ev also has refined(R), the radius the camera refinement ended at. The argument: uses/1, rule_out/2, lesson/3, value_policy/2, predict/2 (with hyp/1, change/2).
% Optional for scoring predictions: next_sign/2 (Ep, Sign) of the episodes that came after.
:- dynamic past_ok/1, uses/1, rule_out/2, lesson/3, value_policy/2, predict/2, past_at/3, past_ev/2, next_sign/2.
:- discontiguous verdict/2.

% ---- (1) observations: what the advisor relies on must be in the logs ----
holds(sym(S))          :- sym(S).
holds(ev(E))           :- ev(E).
holds(setting(K, V))   :- setting(K, V0), V =:= V0.
holds(at(R, B))        :- at(R0, B0), abs(R - R0) =< 0.15, B =:= B0.
holds(past_ev(Ep, E))  :- past_ev(Ep, E0), near(E, E0).
holds(past_ok(Ep))     :- past_ok(Ep).
holds(no(F))           :- \+ holds(F).
holds(lt(A, B))        :- val(A, X), val(B, Y), X < Y.
holds(ge(A, B))        :- val(A, X), val(B, Y), X >= Y.
val(N, N) :- number(N), !.
val(setting(K), V) :- setting(K, V).
near(E, E) :- !.                                    % same term, or the same functor with numbers within 0.15
near(E, E0) :- E =.. [F|A], E0 =.. [F|A0], maplist(near_arg, A, A0).
near_arg(X, Y) :- number(X), number(Y), !, abs(X - Y) =< 0.15.
near_arg(X, X).

verdict(uses(F), ok) :- uses(F), holds(F).
verdict(uses(F), not_in_logs) :- uses(F), \+ holds(F).

% ---- (2) ruled-out causes: the stated reason must hold, and the theory must agree the cause does not apply ----
theory_rejects(C) :- refuted(C, _).
theory_rejects(C) :- \+ (explains(C, S), S \= risk(_)).
verdict(rule_out(C, Why), ok) :- rule_out(C, Why), forall(member(F, Why), holds(F)), theory_rejects(C).
verdict(rule_out(C, Why), reason_false(F)) :- rule_out(C, Why), member(F, Why), \+ holds(F).
verdict(rule_out(C, Why), theory_disagrees) :- rule_out(C, Why), forall(member(F, Why), holds(F)), \+ theory_rejects(C).

% ---- (3) lessons as rules over earlier episodes, each checked on the episodes it cites ----
% underread(Lo, Hi): at the inner edge the camera reads the cube Lo..Hi cm closer than it is
% dim_blue(Vlo, Vhi): the blue cube's brightness can be as low as Vlo..Vhi (pixels rejected by the floor)
lesson_holds_on(underread(Lo, Hi), Ep) :-
    past_at(Ep, R0, _), R0 =< 15.0,
    ( past_ev(Ep, est(R, _)) ; past_ev(Ep, refined(R)) ; past_ev(Ep, dropped_inside(R)) ; past_ev(Ep, gave_up_reach(R)) ),
    D is R0 - R, D >= Lo - 0.4, D =< Hi + 0.4.
lesson_holds_on(dim_blue(Vlo, Vhi), Ep) :-
    past_ev(Ep, blue_below_floor(_, L, H)), L =< Vhi, H >= Vlo.
verdict(lesson(Id, L, Sup), ok) :- lesson(Id, L, Sup), Sup \= [], forall(member(Ep, Sup), lesson_holds_on(L, Ep)).
verdict(lesson(Id, L, Sup), not_supported_by(Bad)) :-
    lesson(Id, L, Sup), findall(Ep, (member(Ep, Sup), \+ lesson_holds_on(L, Ep)), Bad), Bad \= [].

% ---- (4) how the value was chosen: a small vocabulary of policies, each recomputed from the facts ----
% below_observed(M): just below the lowest observed value of the rejected pixels (within margin M)
% restore_true(Id): the radius where it gave up, moved out by the lesson's underread (to the true radius)
% superset_grid: a finer step that contains every value of the old step
% geometric_limit(R): the innermost radius where a look pose exists (the human's rule)
policy_value(blue_v_min, below_observed(M), New) :-
    ev(blue_below_floor(_, Vlo, _)), New < Vlo, Vlo - New =< M.
policy_value(inner_clamp_cm, restore_true(Id), New) :-
    lesson(Id, underread(Lo, Hi), _), findall(R, sym(gave_up_reach(R)), Rs), Rs \= [],
    min_list(Rs, Rmin), max_list(Rs, Rmax), New >= Rmin + Lo - 0.2, New =< Rmax + Hi + 0.2.
policy_value(tilt_step_deg, superset_grid, New) :-
    setting(tilt_step_deg, Cur), New < Cur, 0 =:= Cur mod New,
    forall(sym(no_grasp(R)), ev(grasp_ok(R, New))).
policy_value(inner_clamp_cm, geometric_limit(R), New) :- abs(New - R) =< 0.2.
verdict(value_policy(K, P), ok) :- value_policy(K, P), change(K, V), policy_value(K, P, V).
verdict(value_policy(K, P), value_does_not_follow) :- value_policy(K, P), change(K, V), \+ policy_value(K, P, V).
verdict(value_policy(K, P), no_such_change) :- value_policy(K, P), \+ change(K, _).

% ---- (5) predictions: the reason must hold now; whether it came true is scored on the episodes that followed ----
verdict(predict(E, Why), stated) :- predict(E, Why), forall(member(F, Why), holds(F)), \+ next_sign(_, _).
verdict(predict(E, Why), came_true(Ep)) :- predict(E, Why), forall(member(F, Why), holds(F)), once(next_sign(Ep, E)).
verdict(predict(E, Why), not_observed) :- predict(E, Why), forall(member(F, Why), holds(F)), \+ \+ next_sign(_, _), \+ next_sign(_, E).
verdict(predict(E, Why), reason_false(F)) :- predict(E, Why), member(F, Why), \+ holds(F), !.

item(uses(F)) :- uses(F).
item(rule_out(C, W)) :- rule_out(C, W).
item(lesson(I, L, S)) :- lesson(I, L, S).
item(value_policy(K, P)) :- value_policy(K, P).
item(predict(E, W)) :- predict(E, W).

argue_report :-
    forall(item(I), forall(verdict(I, V), (print(check(I, V)), nl))).
