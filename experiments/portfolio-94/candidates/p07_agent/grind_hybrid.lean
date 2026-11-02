lemma Typing.progress (der : Typing [] t τ) : t.Value ∨ ∃ t', t ⭢βᵛ t' := by
  generalize eq : [] = Γ at der
  let lc := der.wf.2.1
  induction der <;> subst eq
  case var mem => simp at mem
  case app l r il ir =>
    right
    rcases il rfl with vl | ⟨t', hl⟩
    · obtain ⟨_, _, rfl⟩ := l.canonical_form_abs vl
      rcases ir rfl with vr | ⟨t', hr⟩
      · exact ⟨_, .abs vl.lc vr⟩
      · exact ⟨_, .appᵣ vl hr⟩
    · exact ⟨_, .appₗ r.wf.2.1 hl⟩
  case abs | tabs => left; constructor; exact lc
  case tapp => grind only [→ Typing.canonical_form_tabs, → Sub.wf, → Ty.Wf.lc,
    → Value.lc, → Red.tabs, → Red.tapp]
  case let' =>
    have := (body_let.mp lc).2
    grind only [→ Red.let_body, → Red.let_bind]
  case case der _ _ ih _ _ =>
    right
    obtain ⟨_, hb₂, hb₃⟩ := body_case.mp lc
    rcases ih rfl with v | ⟨t', h⟩
    · obtain ⟨t', rfl | rfl⟩ := der.canonical_form_sum v
      all_goals cases v
      all_goals solve_by_elim [Exists.intro, Term.Red.case_inl, Term.Red.case_inr]
    · exact ⟨_, .case h hb₂ hb₃⟩
  all_goals grind only [→ Value.inl, → Value.inr, → Red.inl, → Red.inr]
