lemma Typing.progress (der : Typing [] t τ) : t.Value ∨ ∃ t', t ⭢βᵛ t' := by
  let lc := der.wf.2.1
  induction' der
  case var mem => simp at mem
  case app l r il ir =>
    right
    rcases il with vl | ⟨t', hl⟩
    · obtain ⟨_, _,⟩ := l.canonical_form_abs vl
      rcases ir with vr | ⟨t', hr⟩
      · exact ⟨_, .abs vl.lc vr⟩
      · exact ⟨_, .appᵣ vl hr⟩
    · exact ⟨_, .appₗ r.wf.2.1 hl⟩
  case tapp der sub ih =>
    right
    rcases ih with v | ⟨t', h⟩
    · obtain ⟨_, _,⟩ := der.canonical_form_tabs v
      exact ⟨_, .tabs v.lc sub.wf.2.1.lc⟩
    · exact ⟨_, .tapp sub.wf.2.1.lc h⟩
  case' let' ih _ | inl ih | inr ih =>
    try have hb := (body_let.mp lc).2
    rcases ih with v | ⟨_, h⟩
  case case der _ _ ih _ _ =>
    right
    obtain ⟨_, hb₂, hb₃⟩ := body_case.mp lc
    rcases ih with v | ⟨t', h⟩
    · obtain ⟨t', |⟩ := der.canonical_form_sum v
      all_goals cases v
      all_goals solve_by_elim [Exists.intro, Term.Red.case_inl, Term.Red.case_inr]
    · exact ⟨_, .case h hb₂ hb₃⟩
  all_goals first
  | left; constructor; assumption
  | right; constructor
    first | apply Red.let_body <;> assumption | constructor <;> assumption
  | rename_i ih; exact ih
