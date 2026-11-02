lemma Typing.progress (der : Typing [] t τ) : t.Value ∨ ∃ t', t ⭢βᵛ t' := by
  generalize eq : [] = Γ at der
  let lc := der.wf.2.1
  induction der <;> subst eq
  all_goals clear_value lc
  all_goals grind only [Typing.canonical_form_abs, Typing.canonical_form_tabs,
    Typing.canonical_form_sum, body_let, body_case, → Typing.wf, → Sub.wf,
    → Ty.Wf.lc, → Value.lc, cases Value, Value.abs, Value.tabs, Value.inl, Value.inr,
    Red.appₗ, Red.appᵣ, Red.abs, Red.tabs, Red.tapp, Red.let_bind, Red.let_body,
    Red.inl, Red.inr, Red.case, Red.case_inl, Red.case_inr, = Option.mem_def, = dlookup_nil]
