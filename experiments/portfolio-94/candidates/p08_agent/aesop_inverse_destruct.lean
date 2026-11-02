theorem parallelReduction_diamond : Diamond ParallelReduction := by
  intro a a₁ a₂ h₁ h₂
  induction h₁ generalizing a₂
  case refl => use a₂, h₂, ParallelReduction.refl a₂
  all_goals cases h₂
  all_goals aesop (config := {enableSimp := false}) (add safe [destruct I_irreducible, destruct Ka_irreducible, destruct Sab_irreducible], 50% constructors ParallelReduction)
