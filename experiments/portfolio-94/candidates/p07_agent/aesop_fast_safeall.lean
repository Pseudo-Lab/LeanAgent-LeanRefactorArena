lemma Typing.progress (der : Typing [] t τ) : t.Value ∨ ∃ t', t ⭢βᵛ t' := by
  generalize eq : [] = Γ at der
  let lc := der.wf.2.1
  induction der <;> subst eq
  all_goals clear_value lc
  case var mem => simp at mem
  all_goals simp_all only [true_implies, body_let, body_case]
  all_goals aesop (config := {enableSimp := false}) (add norm [body_let, body_case], safe [cases (cases_patterns := [Value (.inl _), Value (.inr _)]) Value, forward Typing.wf, forward Sub.wf, forward Ty.Wf.lc,
    forward Value.lc, forward Typing.canonical_form_abs,
    forward Typing.canonical_form_tabs, forward Typing.canonical_form_sum],
    safe [constructors Value, constructors Red]) (rule_sets := [-default])
