lemma Typing.progress (der : Typing [] t τ) : t.Value ∨ ∃ t', t ⭢βᵛ t' := by
  generalize eq : [] = Γ at der
  let lc := der.wf.2.1
  induction der <;> subst eq
  all_goals clear_value lc
  all_goals aesop (add norm [body_let, body_case], safe 100 cases Value, safe [forward Typing.wf, forward Sub.wf, forward Ty.Wf.lc,
    forward Value.lc, forward Typing.canonical_form_abs,
    forward Typing.canonical_form_tabs, forward Typing.canonical_form_sum],
    50% [constructors Value, constructors Red]) (rule_sets := [-default])
