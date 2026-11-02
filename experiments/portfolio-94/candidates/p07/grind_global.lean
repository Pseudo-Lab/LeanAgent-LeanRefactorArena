lemma Typing.progress (der : Typing [] t τ) : t.Value ∨ ∃ t', t ⭢βᵛ t' := by
  generalize eq : [] = Γ at der
  let lc := der.wf.2.1
  induction der <;> subst eq
  all_goals grind [Typing.canonical_form_abs, Typing.canonical_form_tabs,
    Typing.canonical_form_sum, body_let, body_case]
