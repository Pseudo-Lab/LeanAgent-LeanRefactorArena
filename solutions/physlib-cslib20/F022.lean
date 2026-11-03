theorem parallelReduction_diamond : Diamond ParallelReduction := by
  intro a a₁ a₂ h₁ h₂
  induction h₁ generalizing a₂
  case refl => use a₂, h₂, ParallelReduction.refl a₂
  all_goals cases h₂
  case' par.par iha ihb _ _ ha'' hb'' =>
    obtain ⟨_, _, _⟩ := iha ha''
    obtain ⟨_, _, _⟩ := ihb hb''
    constructor
    constructor <;> apply ParallelReduction.par <;> assumption
  case' par.red_I | red_I.par =>
    cases I_irreducible _ ‹_›
    constructor
    constructor <;> first | apply ParallelReduction.red_I | assumption
  case' par.red_K | red_K.par =>
    obtain ⟨_, _, rfl⟩ := Ka_irreducible _ _ ‹_›
    constructor
    constructor <;> first | apply ParallelReduction.red_K | assumption
  case' par.red_S | red_S.par =>
    obtain ⟨_, _, _, _, rfl⟩ := Sab_irreducible _ _ _ ‹_›
    constructor
    constructor <;> first
    | apply ParallelReduction.red_S
    | apply ParallelReduction.par <;> apply ParallelReduction.par <;> assumption
  all_goals
    constructor
    constructor
    constructor
    constructor <;> assumption
