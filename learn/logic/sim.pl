% sim.pl — how alike two advisors' arguments are (prototype, 2026-11-04). Loaded after rules.pl and argue.pl.
%
% The two arguments are arg(a, Term) and arg(b, Term), Term as in argue.pl (uses/1, rule_out/2, lesson/3,
% value_policy/2, predict/2) plus change/2. Three layers, reported separately (never summed into one score):
%   layer 1  the conclusion: same setting, same direction, value difference over the setting's range
%   layer 2  the parts of the reason: Jaccard of the observations (numbers equal within 0.15, near/2),
%            of the ruled-out causes, of the predicted effects; overlap of the lessons' intervals; same value policy
%   layer 3  meaning (in sim_support/2, run by argue_sim.py with only one advisor's observations as the evidence):
%            does A's evidence alone, with the theory, derive B's change
:- dynamic arg/2, range/3.

matched(F, L) :- member(G, L), near(F, G), !.
jaccard(LA, LB, J) :-
    include([F]>>matched(F, LB), LA, M), length(M, I), length(LA, NA), length(LB, NB),
    U is NA + NB - I, ( U =:= 0 -> J = none ; J is I / U ).

% ---- layer 1 ----
conclusion(K, Dir, Diff) :-
    arg(a, change(K, VA)), arg(b, change(K, VB)), setting(K, Cur),
    sgn(VA - Cur, SA), sgn(VB - Cur, SB), ( SA =:= SB -> Dir = same ; Dir = opposite ),
    ( range(K, Lo, Hi) -> Diff is abs(VA - VB) / (Hi - Lo) ; Diff is abs(VA - VB) ).
sgn(X, S) :- V is X, ( V > 0 -> S = 1 ; V < 0 -> S = -1 ; S = 0 ).
same_conclusion :- arg(a, change(K, _)), conclusion(K, same, _), \+ (arg(b, change(K2, _)), \+ arg(a, change(K2, _))).

% ---- layer 2 ----
uses_j(J)     :- findall(F, arg(a, uses(F)), A), findall(F, arg(b, uses(F)), B), jaccard(A, B, J).
rule_out_j(J) :- findall(C, arg(a, rule_out(C, _)), A0), sort(A0, A), findall(C, arg(b, rule_out(C, _)), B0), sort(B0, B),
                 jaccard(A, B, J).
predict_j(J)  :- findall(E, arg(a, predict(E, _)), A0), sort(A0, A), findall(E, arg(b, predict(E, _)), B0), sort(B0, B),
                 jaccard(A, B, J).
lesson_ov(O) :-
    ( arg(a, lesson(_, underread(L1, H1), _)), arg(b, lesson(_, underread(L2, H2), _)) ->
        I is max(0, min(H1, H2) - max(L1, L2)), U is max(H1, H2) - min(L1, L2), O is I / U
    ; \+ arg(a, lesson(_, _, _)), \+ arg(b, lesson(_, _, _)) -> O = none
    ; O = 0 ).
policy_same(S) :-
    ( arg(a, value_policy(K, PA)), arg(b, value_policy(K, PB)) ->
        functor(PA, FA, _), functor(PB, FB, _), ( FA == FB -> S = yes ; S = no(FA, FB) )
    ; S = none ).

% ---- layer 3 (the facts hold only the evidence of one advisor, the change is the other's) ----
sim_support(K, V) :-
    minimal_explanation(H), member(C, H), setting_cause(C, K, Dir), setting(K, Cur), dir_ok(Dir, Cur, V),
    effective(C, K, V), !.

sim_report :-
    forall(conclusion(K, D, X), (print(conclusion(K, D, X)), nl)),
    ( same_conclusion -> print(same_conclusion(yes)) ; print(same_conclusion(no)) ), nl,
    uses_j(U), print(uses_jaccard(U)), nl,
    rule_out_j(R), print(rule_out_jaccard(R)), nl,
    lesson_ov(L), print(lesson_overlap(L)), nl,
    policy_same(P), print(policy_same(P)), nl,
    predict_j(Q), print(predict_jaccard(Q)), nl.
