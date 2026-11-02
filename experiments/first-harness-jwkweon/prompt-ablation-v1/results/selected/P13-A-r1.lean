theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  classical
  obtain ⟨B, T, hb⟩ := boundedu
  let f : ℕ → ℤ × ℤ × ℤ × ℤ := fun n => (u n, u (n+1), u (n+2), u (n+3))
  have hf : Set.Finite (Set.range f) := by
    apply (Set.finite_Icc (B,B,B,B) (T,T,T,T)).subset
    rintro x ⟨n, rfl⟩
    exact ⟨⟨(hb _).1, (hb _).1, (hb _).1, (hb _).1⟩,
      ⟨(hb _).2, (hb _).2, (hb _).2, (hb _).2⟩⟩
  have hc : ∃ i j, i < j ∧ f i = f j := by
    by_contra! h
    apply Set.not_infinite.mpr hf
    apply Set.infinite_range_of_injective
    intro i j he
    by_contra hne
    rcases lt_or_gt_of_ne hne with hij | hij
    · exact h i j hij he
    · exact h j i hij he.symm
  obtain ⟨i, j, hij, he⟩ := hc
  simp only [f, Prod.mk.injEq] at he
  have hall : ∀ m, u (i+m) = u (j+m) := by
    intro m
    induction m using Nat.strong_induction_on with
    | h m ih =>
      by_cases hm : m < 4
      · interval_cases m
        · simpa using he.1
        · exact he.2.1
        · exact he.2.2.1
        · exact he.2.2.2
      · have e (k : ℕ) (hk : 0 < k) (hkm : k ≤ m) : u (i+m-k) = u (j+m-k) := by
          rw [Nat.add_sub_assoc hkm, Nat.add_sub_assoc hkm]
          exact ih (m-k) (by omega)
        apply @Int.cast_injective ℝ _ _
        rw [(hu (i+m) (by omega)).1, (hu (j+m) (by omega)).1]
        rw [e 1 (by decide) (by omega), e 2 (by decide) (by omega),
          e 3 (by decide) (by omega), e 4 (by decide) (by omega)]
  refine ⟨i, j-i, by omega, ?_⟩
  intro n hn
  convert (hall (n-i)).symm using 1 <;> congr 1 <;> omega
