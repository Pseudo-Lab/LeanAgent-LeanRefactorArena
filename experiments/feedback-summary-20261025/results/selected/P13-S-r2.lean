theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  classical
  obtain ⟨B, T, hB⟩ := boundedu
  let f : ℕ → Fin 4 → ℤ := fun n k => u (n+k)
  have hf : (Set.range f).Finite := by
    apply (Set.finite_Icc (fun _ : Fin 4 => B) (fun _ => T)).subset
    rintro x ⟨n, rfl⟩
    exact ⟨fun k => (hB _).1, fun k => (hB _).2⟩
  obtain ⟨i, j, hij, he⟩ : ∃ i j, i < j ∧ f i = f j := by
    by_contra! h
    apply Set.not_infinite.mpr hf
    apply Set.infinite_range_of_injective
    intro i j he
    rcases lt_trichotomy i j with hij | hij | hij
    · exact False.elim (h i j hij he)
    · exact hij
    · exact False.elim (h j i hij he.symm)
  have hr (n : ℕ) : (u (n+4) : ℝ) =
      (u (n+3) + u (n+2) + u (n+1) * u n) /
      (u (n+3) * u (n+2) + u (n+1) + u n) := by
    simpa [Nat.add_sub_assoc] using (hu (n+4) (by omega)).1
  have hp (m : ℕ) : u (i+m) = u (j+m) := by
    induction m using Nat.strong_induction_on with
    | h m ih =>
      match m with
      | 0 | 1 | 2 | 3 => exact congrFun he ⟨_,by decide⟩
      | m+4 =>
        apply Int.cast_injective (α := ℝ)
        simp only [← Nat.add_assoc]
        rw [hr, hr]
        simp only [Nat.add_assoc, ih m (by omega), ih (m+1) (by omega),
          ih (m+2) (by omega), ih (m+3) (by omega)]
  refine ⟨i, j-i, by omega, ?_⟩
  intro n hn
  have h := (hp (n-i)).symm
  convert h using 1 <;> congr 1 <;> omega
