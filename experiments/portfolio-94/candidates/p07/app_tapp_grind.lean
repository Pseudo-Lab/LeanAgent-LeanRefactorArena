lemma Typing.progress (der : Typing [] t τ) : t.Value ∨ ∃ t', t ⭢βᵛ t' := by
  generalize eq : [] = Γ at der
  let lc := der.wf.2.1
  induction der <;> subst eq
  case var mem => simp at mem
  case app l r il ir =>
    have hr := r.wf.2.1
    grind [Typing.canonical_form_abs]
  case tapp der sub ih =>
    have hs := sub.wf.2.1.lc
    grind [Typing.canonical_form_tabs]
  case' let' ih _ | inl ih | inr ih =>
    try have hb := (body_let.mp lc).2
    rcases ih rfl with v | ⟨_, h⟩
  case case der _ _ ih _ _ =>
    right
    obtain ⟨_, hb₂, hb₃⟩ := body_case.mp lc
    rcases ih rfl with v | ⟨t', h⟩
    · obtain ⟨t', rfl | rfl⟩ := der.canonical_form_sum v
      all_goals cases v
      all_goals solve_by_elim [Exists.intro, Term.Red.case_inl, Term.Red.case_inr]
    · exact ⟨_, .case h hb₂ hb₃⟩
  all_goals first
  | left; constructor; assumption
  | right; constructor
    first | apply Red.let_body <;> assumption | constructor <;> assumption
  | rename_i ih; exact ih rfl
