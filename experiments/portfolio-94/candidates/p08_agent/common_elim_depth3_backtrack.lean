theorem parallelReduction_diamond : Diamond ParallelReduction := by
  intro a a₁ a₂ h₁ h₂
  induction h₁ generalizing a₂
  case refl => use a₂, h₂, ParallelReduction.refl a₂
  all_goals cases h₂
  case' par.par iha ihb _ _ ha'' hb'' =>
    exact (iha ha'').elim fun _ ha => (ihb hb'').elim fun _ hb =>
      ⟨_, ParallelReduction.par ha.1 hb.1, ParallelReduction.par ha.2 hb.2⟩
  case' par.red_I ha' _ | red_I.par ha' _ => cases I_irreducible _ ha'
  case' par.red_K ha' _ | red_K.par ha' _ =>
    obtain ⟨_, h, rfl⟩ := Ka_irreducible _ _ ha'
  case' par.red_S hb' _ _ _ ha' _ | red_S.par ha' hb' =>
    obtain ⟨_, _, ha, hc, rfl⟩ := Sab_irreducible _ _ _ ha'
  all_goals first
  | (refine ⟨_, ParallelReduction.refl _, ?_⟩; constructor <;> assumption)
  | (constructor; constructor <;> solve_by_elim (maxDepth := 3) [ParallelReduction.red_I, ParallelReduction.red_K, ParallelReduction.red_S, ParallelReduction.par])
