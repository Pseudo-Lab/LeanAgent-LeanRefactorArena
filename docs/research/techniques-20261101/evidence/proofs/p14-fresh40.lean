theorem putnam_1964_b2
(S : Type*) [Fintype S] [Nonempty S]
(P : Finset (Set S))
(hPP : ∀ T ∈ P, ∀ U ∈ P, T ∩ U ≠ ∅)
(hPS : ¬∃ T : Set S, T ∉ P ∧ (∀ U ∈ P, T ∩ U ≠ ∅))
: (P.card = 2 ^ (Fintype.card S - 1)) := by
  classical
  have hi : P.image compl = Pᶜ := by
    ext T
    obtain ⟨T, rfl⟩ := compl_surjective T
    simp only [Finset.mem_image, compl_injective.eq_iff, exists_eq_right, Finset.mem_compl]
    constructor
    · intro ht htc
      simpa using hPP T ht Tᶜ htc
    · intro htc
      by_contra ht
      refine hPS ⟨T, ht, fun U hu hTU =>
        hPS ⟨Tᶜ, htc, fun V hv hzero => hPP U hu V hv ?_⟩⟩
      rw [← Set.disjoint_iff_inter_eq_empty] at hTU hzero ⊢
      exact hTU.symm.mono_right (disjoint_compl_left_iff_subset.mp hzero)
  have hn := Finset.card_compl P
  rw [← hi, Finset.card_image_of_injective _ compl_injective,
    Fintype.card_set,
    ← Nat.sub_add_cancel (m := 1) Fintype.card_pos, pow_succ] at hn
  omega
