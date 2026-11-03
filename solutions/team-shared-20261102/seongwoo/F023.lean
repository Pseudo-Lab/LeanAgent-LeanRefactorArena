theorem bisimilarity_congr_choice :
    (p ~[lts (defs := defs)] q) → (choice p r) ~[lts (defs := defs)] (choice q r) := by
  intro h
  exists _, ChoiceBisim.choice h
  intro s1 s2 hr μ
  cases hr
  case' choice hb =>
    constructor <;> intro s' ht <;> cases ht <;> rename_i ht
    all_goals
      try exact ⟨_, ht.choiceR, .bisim (HomBisimilarity.refl _)⟩
  case' bisim hb =>
    constructor <;> intro s' ht
  all_goals
    obtain ⟨t, ht, h'⟩ := by
      first | exact hb.follow_fst ht | exact hb.follow_snd ht
    refine ⟨t, ?_, .bisim h'⟩
    try apply Tr.choiceL
    assumption
