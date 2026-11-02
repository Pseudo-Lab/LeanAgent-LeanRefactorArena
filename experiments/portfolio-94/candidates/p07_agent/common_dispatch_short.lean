lemma Typing.progress (der : Typing [] t τ) : t.Value ∨ ∃ t', t ⭢βᵛ t' := by
  generalize eq : [] = Γ at der
  let lc := der.wf.2.1
  induction der <;> subst eq
  case var mem => simp at mem
  case' app l r il ir =>
    have := r.wf.2.1
    rcases il rfl with v | ⟨_, h⟩
    case' inl =>
      obtain ⟨_, _, rfl⟩ := l.canonical_form_abs v
      have := v.lc
      rcases ir rfl with v | ⟨_, h⟩
  case' tapp der sub ih =>
    have := sub.wf.2.1.lc
    rcases ih rfl with v | ⟨_, h⟩
    case' inl =>
      obtain ⟨_, _, rfl⟩ := der.canonical_form_tabs v
      have := v.lc
  case' let' ih _ | inl ih | inr ih =>
    try have := (body_let.mp lc).2
    rcases ih rfl with v | ⟨_, h⟩
  case' case der _ _ ih _ _ =>
    obtain ⟨_, hb₂, hb₃⟩ := body_case.mp lc
    rcases ih rfl with v | ⟨_, h⟩
    case' inl =>
      obtain ⟨_, rfl | rfl⟩ := der.canonical_form_sum v
      all_goals cases v
  all_goals first
  | rename_i ih; exact ih rfl
  | left; constructor; assumption
  | right; constructor
    first
    | solve_by_elim [Red.abs, Red.tabs, Red.appᵣ, Red.let_body, Red.case_inl, Red.case_inr]
    | constructor <;> assumption
