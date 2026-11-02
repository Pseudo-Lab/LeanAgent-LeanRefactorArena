theorem parallelReduction_diamond : Diamond ParallelReduction := by
  intro a a₁ a₂ h₁ h₂
  induction h₁ generalizing a₂
  case refl => exact ⟨_, h₂, ParallelReduction.refl _⟩
  all_goals cases h₂
  case' par.par iha ihb _ _ ha'' hb'' =>
    have := iha ha''
    have := ihb hb''
  all_goals unfold Join at *
  all_goals aesop (config := {enableSimp := false}) (add safe [destruct I_irreducible, destruct Ka_irreducible, destruct Sab_irreducible], 90% [apply ParallelReduction.red_I, apply ParallelReduction.red_K, apply ParallelReduction.red_S], 50% apply ParallelReduction.par, 5% apply ParallelReduction.refl)
