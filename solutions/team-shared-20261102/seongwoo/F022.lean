theorem parallelReduction_diamond : Diamond ParallelReduction := by
  intro a a₁ a₂ h₁ h₂
  induction h₁ generalizing a₂
  · use a₂, h₂, ParallelReduction.refl a₂
  case' par ha' hb' iha ihb =>
    cases h₂
    rotate_left
    · cases I_irreducible _ ha'
      exact ⟨_, ParallelReduction.red_I _, hb'⟩
    · rcases Ka_irreducible _ _ ha' with ⟨_, h, rfl⟩
      exact ⟨_, ParallelReduction.red_K .., h⟩
    · rcases Sab_irreducible _ _ _ ha' with ⟨_, _, ha, hc, rfl⟩
      exact ⟨_, ParallelReduction.red_S ..,
        (ha.par hb').par (hc.par hb')⟩
    next ha'' hb'' =>
      rcases iha ha'' with ⟨a₃, ha⟩
      rcases ihb hb'' with ⟨b₃, hb⟩
      exact ⟨_, ha.1.par hb.1, ha.2.par hb.2⟩
  all_goals try cases h₂
  case red_I.par hc ha =>
    cases I_irreducible _ hc
    exact ⟨_, ha, ParallelReduction.red_I _⟩
  case red_K.par ha hc =>
    rcases Ka_irreducible _ _ ha with ⟨_, h, rfl⟩
    exact ⟨_, h, ParallelReduction.red_K ..⟩
  case red_S.par hd hc =>
    rcases Sab_irreducible _ _ _ hd with ⟨_, _, ha, hb, rfl⟩
    exact ⟨_, (ha.par hc).par (hb.par hc), ParallelReduction.red_S ..⟩
  all_goals exact ⟨_, ParallelReduction.refl _, by constructor <;> assumption⟩
