lemma Typing.progress (der : Typing [] t τ) : t.Value ∨ ∃ t', t ⭢βᵛ t' := by
  generalize eq : [] = Γ at der
  have der' := der
  induction der <;> subst eq
  all_goals replace der' := der'.wf
  case var | sub => grind
  case app t₁ _ _ t₂ l r ih_l ih_r =>
    right
    rcases ih_l rfl l with val_l | ⟨t₁', red_l⟩
    · rcases ih_r rfl r with val_r | ⟨t₂', red_r⟩
      · obtain ⟨σ, t₁, rfl⟩ := l.canonical_form_abs val_l
        exact ⟨t₁ ^ᵗᵗ t₂, by grind⟩
      · exact ⟨t₁.app t₂', by grind⟩
    · exact ⟨t₁'.app t₂, by grind⟩
  case tapp σ' der _ ih =>
    right
    rcases ih rfl der with val | ⟨t', red⟩
    · obtain ⟨_, t, rfl⟩ := der.canonical_form_tabs val
      exact ⟨t ^ᵗᵞ σ', by grind⟩
    · exact ⟨.tapp t' σ', by grind⟩
  case let' t₁ σ t₂ τ L der _ ih _ =>
    right
    rcases ih rfl der with val | ⟨t₁', red⟩
    · exact ⟨t₂ ^ᵗᵗ t₁, by grind⟩
    · exact ⟨t₁'.let' t₂, by grind⟩
  case inl der _ ih | inr der _ ih =>
    rcases ih rfl der with val | ⟨t', red⟩
    · left
      constructor
      exact val
    · right
      exact ⟨_, by constructor; assumption⟩
  case case t₁ _ _ t₂ _ t₃ _ der _ _ ih _ _ =>
    right
    rcases ih rfl der with val | ⟨t₁', red⟩
    · obtain ⟨t₁, h | h⟩ := der.canonical_form_sum val
      · exact ⟨t₂ ^ᵗᵗ t₁, by grind⟩
      · exact ⟨t₃ ^ᵗᵗ t₁, by grind⟩
    · exact ⟨t₁'.case t₂ t₃, by grind⟩
  case abs | tabs =>
    left
    constructor
    grind only []
