theorem putnam_1964_b2
(S : Type*) [Fintype S] [Nonempty S]
(P : Finset (Set S))
(hPP : ∀ T ∈ P, ∀ U ∈ P, T ∩ U ≠ ∅)
(hPS : ¬∃ T : Set S, T ∉ P ∧ (∀ U ∈ P, T ∩ U ≠ ∅))
: (P.card = 2 ^ (Fintype.card S - 1)) := by
  have missing (A : Set S) (hA : A ∉ P) : ∃ U ∈ P, A ∩ U = ∅ := by
    by_contra! h
    exact hPS ⟨A, hA, by simpa only [Set.nonempty_iff_ne_empty] using h⟩
  have h_subset_or_compl : ∀ A : Set S, A ∈ P ∨ Aᶜ ∈ P := by
    intro A
    by_contra! h
    obtain ⟨U, hU, hAU⟩ := missing A h.1
    obtain ⟨V, hV, hAV⟩ := missing Aᶜ h.2
    apply hPP U hU V hV
    apply Set.disjoint_iff_inter_eq_empty.mp
    exact (Set.disjoint_iff_inter_eq_empty.mpr hAV).mono_left
      (Set.disjoint_right.mp (Set.disjoint_iff_inter_eq_empty.mpr hAU))
  classical
  have hcard : P.card = Pᶜ.card := by
    refine Finset.card_bij' (fun A _ => Aᶜ) (fun A _ => Aᶜ) ?_ ?_ ?_ ?_
    · intro A hA
      exact Finset.mem_compl.mpr (fun hAc => hPP A hA Aᶜ hAc (Set.inter_compl_self A))
    · intro A hA
      exact (h_subset_or_compl A).resolve_left (Finset.mem_compl.mp hA)
    · intro A _; exact compl_compl A
    · intro A _; exact compl_compl A
  have hsum : P.card + P.card = 2 ^ Fintype.card S := by
    simpa only [← hcard, Fintype.card_set] using Finset.card_compl_add_card P
  have hn : 0 < Fintype.card S := Fintype.card_pos
  have hpow := pow_succ 2 (Fintype.card S - 1)
  rw [show Fintype.card S - 1 + 1 = Fintype.card S by omega] at hpow
  omega
