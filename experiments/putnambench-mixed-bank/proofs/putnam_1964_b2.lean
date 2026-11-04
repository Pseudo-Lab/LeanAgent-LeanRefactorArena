theorem putnam_1964_b2
(S : Type*) [Fintype S] [Nonempty S]
(P : Finset (Set S))
(hPP : ∀ T ∈ P, ∀ U ∈ P, T ∩ U ≠ ∅)
(hPS : ¬∃ T : Set S, T ∉ P ∧ (∀ U ∈ P, T ∩ U ≠ ∅))
: (P.card = 2 ^ (Fintype.card S - 1)) := by
  classical
  simp only [ne_eq, ← Set.disjoint_iff_inter_eq_empty] at hPP hPS
  have h := (show (P : Set (Set S)).Intersecting from hPP).is_max_iff_card_eq.mp (by
    intro Q hQ hPQ
    apply Finset.Subset.antisymm hPQ
    intro T hT
    by_contra hn
    exact hPS ⟨T, hn, fun U hU => hQ hT (hPQ hU)⟩)
  rw [Fintype.card_set, ← Nat.sub_add_cancel (Fintype.card_pos (α := S)), pow_succ'] at h
  exact Nat.eq_of_mul_eq_mul_left (by decide) h
