lemma Typing.progress (der : Typing [] t τ) : t.Value ∨ ∃ t', t ⭢βᵛ t' := by
  generalize eq : [] = Γ at der
  let lc := der.wf.2.1
  induction der <;> subst eq
  case var mem => simp at mem
  case abs | tabs => left; constructor; exact lc
  case app t₁ _ _ t₂ _ _ _ _ => grind only [→ Typing.wf, → Typing.canonical_form_abs, → Value.lc,
    → Red.abs, → Red.appₗ (t₁ := t₁), → Red.appᵣ (t₂ := t₂)]
  case tapp => grind only [→ Typing.canonical_form_tabs, → Sub.wf, → Ty.Wf.lc,
    → Value.lc, → Red.tabs, → Red.tapp]
  case let' =>
    have := (body_let.mp lc).2
    grind only [→ Red.let_body, → Red.let_bind]
  case case t₁ _ _ t₂ _ t₃ _ _ _ _ _ _ _ =>
    obtain ⟨_, _, _⟩ := body_case.mp lc
    grind only [→ Typing.canonical_form_sum, cases Value,
      → Red.case (t₁ := t₁), → Red.case_inl, → Red.case_inr]
  all_goals grind only [→ Value.inl, → Value.inr, → Red.inl, → Red.inr]
