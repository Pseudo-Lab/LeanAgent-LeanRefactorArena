theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  classical
  obtain ⟨B, T, hB⟩ := boundedu
  let v (n : ℕ) : {z : ℤ // z ∈ Finset.Icc B T} := ⟨u n, Finset.mem_Icc.mpr (hB n)⟩
  let f := fun n : ℕ => (v n, v (n+1), v (n+2), v (n+3))
  have hf := Set.toFinite (Set.range f)
  have hex : ∃ i j, i < j ∧ f i = f j := by
    by_contra! h
    apply hf.not_infinite
    apply Set.infinite_range_of_injective
    intro i j e
    by_contra hne
    rcases lt_or_gt_of_ne hne with hlt | hgt
    · exact h i j hlt e
    · exact h j i hgt e.symm
  obtain ⟨i,j,hij,he⟩ := hex
  simp [f, v] at he
  have hr (n : ℕ) := (hu (n+4) (by omega)).1
  simp [Nat.add_sub_assoc] at hr
  have hall (m : ℕ) : u (i+m) = u (j+m) := by
    induction m using Nat.strong_induction_on with
    | h m ih =>
      match m with
      | 0 => simpa using he.1
      | 1 => exact he.2.1
      | 2 => exact he.2.2.1
      | 3 => exact he.2.2.2
      | m+4 =>
        have hi := hr (i+m)
        have hj := hr (j+m)
        simp only [Nat.add_assoc] at hi hj
        rw [ih (m+3) (by omega), ih (m+2) (by omega), ih (m+1) (by omega), ih m (by omega)] at hi
        exact_mod_cast hi.trans hj.symm
  refine ⟨i, j-i, by omega, ?_⟩
  intro n hn
  convert (hall (n-i)).symm using 1 <;> congr 1 <;> omega
