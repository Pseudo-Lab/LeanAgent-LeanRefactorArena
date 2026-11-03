theorem bisimilarity_congr_choice :
    (p ~[lts (defs := defs)] q) → (choice p r) ~[lts (defs := defs)] (choice q r) := by
  intro h
  exists ChoiceBisim, .choice h
  rintro _ _ (h | h) μ
  all_goals
    apply (Bisimilarity.isBisimulation _ _ h μ).imp
    all_goals
    intro f s t
  iterate 2
    cases t
    exact (f _ ‹_›).imp fun _ => And.imp Tr.choiceL .bisim
    exact ⟨s, Tr.choiceR ‹_›, .bisim (.refl _)⟩
  all_goals exact (f _ t).imp fun _ => And.imp id .bisim
