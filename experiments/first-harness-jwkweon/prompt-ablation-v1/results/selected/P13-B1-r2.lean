theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  classical
  obtain ⟨B, T, hB⟩ := boundedu
  let f : ℕ → ℤ × ℤ × ℤ × ℤ := fun n => (u n, u (n+1), u (n+2), u (n+3))
  have hf : Set.Finite (Set.range f) := by
    apply (Set.finite_mem_finset (Finset.Icc (B,B,B,B) (T,T,T,T))).subset
    rintro x ⟨n, rfl⟩
    simp only [f, Set.mem_setOf_eq, Finset.mem_Icc, Prod.le_def, hB, and_self]
  have hc : ∃ i j, i < j ∧ f i = f j := by
    by_contra! h
    have hi : Function.Injective f := by
      intro i j e
      exact le_antisymm (not_lt.mp (fun hlt => h j i hlt e.symm))
        (not_lt.mp (fun hlt => h i j hlt e))
    exact hf.not_infinite (Set.infinite_range_of_injective hi)
  obtain ⟨i,j,hij,he⟩ := hc
  simp only [f, Prod.mk.injEq] at he
  have step (n : ℕ) : (u (n+4) : ℝ) =
      (u (n+3) + u (n+2) + u (n+1) * u n) /
      (u (n+3) * u (n+2) + u (n+1) + u n) := by
    simpa [Nat.add_sub_assoc] using (hu (n+4) (by omega)).1
  have hs : ∀ m, u (i+m) = u (j+m) ∧ u (i+m+1) = u (j+m+1) ∧
      u (i+m+2) = u (j+m+2) ∧ u (i+m+3) = u (j+m+3) := by
    intro m
    induction m with
    | zero => simpa using he
    | succ m ih =>
      rcases ih with ⟨a,b,c,d⟩
      have e : u (i+m+4) = u (j+m+4) := by
        apply Int.cast_injective (α := ℝ)
        rw [step (i+m), step (j+m), a,b,c,d]
      simpa only [Nat.succ_eq_add_one, Nat.add_assoc] using And.intro b (And.intro c (And.intro d e))
  refine ⟨i, j-i, by omega, ?_⟩
  intro n hn
  have e := (hs (n-i)).1
  simpa only [show i+(n-i)=n by omega, show j+(n-i)=n+(j-i) by omega] using e.symm
