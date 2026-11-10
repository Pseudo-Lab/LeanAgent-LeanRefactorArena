theorem putnam_1964_b2
(S : Type*) [Fintype S] [Nonempty S]
(P : Finset (Set S))
(hPP : ∀ T ∈ P, ∀ U ∈ P, T ∩ U ≠ ∅)
(hPS : ¬∃ T : Set S, T ∉ P ∧ (∀ U ∈ P, T ∩ U ≠ ∅))
: (P.card = 2 ^ (Fintype.card S - 1)) := by
  apply Nat.mul_right_cancel Nat.two_pos
  rw [Nat.pow_pred_mul Fintype.card_pos, Nat.mul_comm P.card, ← Fintype.card_set]
  apply (Set.Intersecting.is_max_iff_card_eq ?_).mp
  · intro Q hQ hPQ
    apply Finset.Subset.antisymm hPQ
    simp only [Set.Intersecting, Set.disjoint_iff_inter_eq_empty, Finset.mem_coe] at hQ
    grind [Finset.subset_iff]
  · simpa only [Set.Intersecting, Set.disjoint_iff_inter_eq_empty] using hPP
