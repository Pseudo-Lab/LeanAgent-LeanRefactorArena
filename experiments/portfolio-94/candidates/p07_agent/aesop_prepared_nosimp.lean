lemma Typing.progress (der : Typing [] t τ) : t.Value ∨ ∃ t', t ⭢βᵛ t' := by
  generalize eq : [] = Γ at der
  let lc := der.wf.2.1
  induction der <;> subst eq
  case var mem => simp at mem
  case' let' => have := (body_let.mp lc).2
  case' case der _ _ ih _ _ =>
    obtain ⟨_, hb₂, hb₃⟩ := body_case.mp lc
    rcases ih rfl with v | ⟨_, h⟩
    case' inl =>
      obtain ⟨_, rfl | rfl⟩ := der.canonical_form_sum v
      all_goals cases v
  all_goals clear_value lc
  all_goals simp_all only [true_implies]
  all_goals aesop (config := {enableSimp := false}) (rule_sets := [-default]) (add safe [forward Typing.wf, forward Sub.wf, forward Ty.Wf.lc,
      forward Value.lc, forward Typing.canonical_form_abs, forward Typing.canonical_form_tabs],
      50% [constructors Value, constructors Red])
