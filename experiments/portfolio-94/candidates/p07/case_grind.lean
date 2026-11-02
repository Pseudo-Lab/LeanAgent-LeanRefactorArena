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
  case tapp der sub ih =>
    right
    rcases ih rfl with v | ⟨t', h⟩
    · obtain ⟨_, _, rfl⟩ := der.canonical_form_tabs v
      exact ⟨_, .tabs v.lc sub.wf.2.1.lc⟩
    · exact ⟨_, .tapp sub.wf.2.1.lc h⟩
  case' let' ih _ | inl ih | inr ih =>
    try have hb := (body_let.mp lc).2
    rcases ih rfl with v | ⟨_, h⟩
  case case der _ _ ih _ _ =>
    obtain ⟨_, hb₂, hb₃⟩ := body_case.mp lc
    grind [Typing.canonical_form_sum]
  all_goals first
  | left; constructor; assumption
  | right; constructor
    first | apply Red.let_body <;> assumption | constructor <;> assumption
  | rename_i ih; exact ih rfl
