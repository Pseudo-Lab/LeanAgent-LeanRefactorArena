theorem parallelReduction_diamond : Diamond ParallelReduction := by
  intro a a₁ a₂ h₁ h₂
  induction h₁ generalizing a₂
  case refl => exact ⟨_, h₂, ParallelReduction.refl _⟩
  all_goals cases h₂
  case' par.par iha ihb _ _ ha'' hb'' =>
    have := iha ha''
    have := ihb hb''
  all_goals unfold Join at *
  all_goals aesop (add safe [forward I_irreducible, forward Ka_irreducible, forward Sab_irreducible], 50% constructors ParallelReduction)
