theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  classical
  obtain ⟨B, T, hB⟩ := boundedu
  let f : ℕ → Fin 4 → ℤ := fun n k => u (n+k)
  have hf : Set.Finite (Set.range f) := by
    apply (Set.finite_Icc (fun _ : Fin 4 => B) (fun _ => T)).subset
    rintro x ⟨n, rfl⟩
    exact ⟨fun k => (hB (n+k)).1, fun k => (hB (n+k)).2⟩
  have hp : ∃ i j, i < j ∧ f i = f j := by
    by_contra! h
    apply (Set.infinite_range_of_injective ?_) hf
    intro i j he
    exact le_antisymm (le_of_not_gt fun hj => h j i hj he.symm)
      (le_of_not_gt fun hi => h i j hi he)
  obtain ⟨i, j, hij, heq⟩ := hp
  have he : ∀ m, u (i+m) = u (j+m) := by
    intro m
    induction m using Nat.strong_induction_on with
    | h m ih =>
      by_cases hm : m < 4
      · exact congrFun heq ⟨m, hm⟩
      · have hprev (k : ℕ) (hk : k < 4) : u (i+m-(k+1)) = u (j+m-(k+1)) := by
          simp only [Nat.add_sub_assoc (by omega : k+1 ≤ m)]
          exact ih (m-(k+1)) (by omega)
        apply (Int.cast_injective : Injective (Int.cast : ℤ → ℝ))
        rw [(hu (i+m) (by omega)).1, (hu (j+m) (by omega)).1,
          hprev 0 (by decide), hprev 1 (by decide), hprev 2 (by decide), hprev 3 (by decide)]
  refine ⟨i, j-i, by omega, ?_⟩
  intro n hn
  convert (he (n-i)).symm using 1 <;> congr 1 <;> omega
