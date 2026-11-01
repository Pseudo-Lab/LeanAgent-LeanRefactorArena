theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  obtain ⟨B,T,h⟩ := boundedu
  let s : ℕ → Fin 4 → Set.Icc B T := fun n k => ⟨u (n+k),h (n+k)⟩
  obtain ⟨i,j,hij,hs⟩ : ∃ i j, i < j ∧ s i = s j := by
    obtain ⟨i,j,hij,hs⟩ := Finite.exists_ne_map_eq_of_infinite s
    rcases lt_or_gt_of_ne hij with hlt | hgt
    · exact ⟨i,j,hlt,hs⟩
    · exact ⟨j,i,hgt,hs.symm⟩
  have eqs k : u (i+k) = u (j+k) := by
    refine Nat.strong_induction_on k ?_
    intro k ih
    by_cases hk : k < 4
    · exact congrArg Subtype.val (congrFun hs ⟨k,hk⟩)
    · apply Int.cast_injective (α := ℝ)
      rw [(hu (i+k) (by omega)).1, (hu (j+k) (by omega)).1]
      simp (disch := omega) only [Nat.add_sub_assoc, ih]
  refine ⟨i,j-i,by omega,?_⟩
  intro n hn
  convert (eqs (n-i)).symm using 2 <;> omega
