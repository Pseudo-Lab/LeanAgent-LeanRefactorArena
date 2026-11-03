theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  obtain ⟨B, T, hb⟩ := boundedu
  let f : ℕ → ℤ × ℤ × ℤ × ℤ := fun n => (u n, u (n+1), u (n+2), u (n+3))
  have hf : Set.Finite (Set.range f) := by
    apply (Set.finite_Icc (B,B,B,B) (T,T,T,T)).subset
    rintro x ⟨n, rfl⟩
    exact ⟨⟨(hb n).1, (hb (n+1)).1, (hb (n+2)).1, (hb (n+3)).1⟩,
      (hb n).2, (hb (n+1)).2, (hb (n+2)).2, (hb (n+3)).2⟩
  have hc : ∃ i j, i < j ∧ f i = f j := by
    by_contra! hc
    apply Set.not_infinite.mpr hf
    apply Set.infinite_range_of_injective
    intro i j he
    exact le_antisymm (le_of_not_gt (fun h => hc j i h he.symm))
      (le_of_not_gt (fun h => hc i j h he))
  obtain ⟨i, j, hij, he⟩ := hc
  simp only [f, Prod.mk.injEq] at he
  have h : ∀ m, u (i+m) = u (j+m) := by
    intro m
    induction m using Nat.strong_induction_on with
    | h m ih =>
      match m with
      | 0 => exact he.1
      | 1 => exact he.2.1
      | 2 => exact he.2.2.1
      | 3 => exact he.2.2.2
      | m+4 =>
        have hi := (hu (i+m+4) (by omega)).1
        have hj := (hu (j+m+4) (by omega)).1
        norm_num only [Nat.add_sub_assoc, Nat.add_zero] at hi hj
        simp only [Nat.add_assoc] at hi hj
        rw [ih (m+3) (by omega), ih (m+2) (by omega), ih (m+1) (by omega), ih m (by omega)] at hi
        exact Int.cast_injective (hi.trans hj.symm)
  refine ⟨i, j-i, by omega, ?_⟩
  intro n hn
  convert (h (n-i)).symm using 1 <;> congr 1 <;> omega
