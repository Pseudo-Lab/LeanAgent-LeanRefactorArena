theorem parallelReduction_diamond : Diamond ParallelReduction := by
  intro a a₁ a₂ h₁ h₂
  induction a generalizing a₁ a₂
  all_goals cases h₁
  all_goals first | exact ⟨_, h₂, ParallelReduction.refl _⟩ | skip
  all_goals cases h₂
  case' app.par.par a b iha ihb a' b' ha' hb' a'' b'' ha'' hb'' =>
    exact (iha ha' ha'').elim fun _ ha => (ihb hb' hb'').elim fun _ hb =>
      ⟨_, ParallelReduction.par ha.1 hb.1, ParallelReduction.par ha.2 hb.2⟩
  case' par.red_I ha' _ | red_I.par ha' _ =>
    cases I_irreducible _ ha'
    constructor
    constructor <;> first | assumption | exact ParallelReduction.red_I _
  case' par.red_K ha' _ | red_K.par ha' _ =>
    obtain ⟨_, h, rfl⟩ := Ka_irreducible _ _ ha'
    constructor
    constructor <;> first | exact h | exact ParallelReduction.red_K _ _
  case' par.red_S hb' _ _ _ ha' _ | red_S.par ha' hb' =>
    obtain ⟨_, _, ha, hc, rfl⟩ := Sab_irreducible _ _ _ ha'
    constructor
    constructor <;> first
    | exact ParallelReduction.red_S ..
    | exact ParallelReduction.par (ParallelReduction.par ha hb') (ParallelReduction.par hc hb')
  all_goals exact ⟨_, ParallelReduction.refl _, by constructor <;> assumption⟩
