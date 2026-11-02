theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  obtain ⟨B, T, hB⟩ := boundedu
  let f : ℕ → ℤ × ℤ × ℤ × ℤ := fun n => (u n, u (n+1), u (n+2), u (n+3))
  have hf : Set.Finite (Set.range f) := by
    apply (Set.finite_Icc (B,B,B,B) (T,T,T,T)).subset
    rintro x ⟨n, rfl⟩
    exact ⟨⟨(hB n).1, (hB (n+1)).1, (hB (n+2)).1, (hB (n+3)).1⟩,
      ⟨(hB n).2, (hB (n+1)).2, (hB (n+2)).2, (hB (n+3)).2⟩⟩
  have hc : ∃ i j, i < j ∧ f i = f j := by
    by_contra! h
    apply hf.not_infinite
    apply Set.infinite_range_of_injective
    intro i j he
    rcases lt_trichotomy i j with hij | hij | hij
    · exact False.elim (h i j hij he)
    · exact hij
    · exact False.elim (h j i hij he.symm)
  obtain ⟨i,j,hij,he⟩ := hc
  have hs : ∀ m, f (i+m) = f (j+m) := by
    intro m
    induction m with
    | zero => simpa using he
    | succ m ih =>
      simp only [f, Prod.mk.injEq] at ih ⊢
      simp only [Nat.add_succ, Nat.succ_add]
      refine ⟨ih.2.1, ih.2.2.1, ih.2.2.2, ?_⟩
      apply Int.cast_injective (α := ℝ)
      rw [(hu (i+m+4) (by omega)).1, (hu (j+m+4) (by omega)).1]
      simp [Nat.add_sub_assoc, ih]
  refine ⟨i, j-i, by omega, ?_⟩
  intro n hn
  have h := congrArg Prod.fst (hs (n-i)).symm
  simpa only [f, show i+(n-i)=n by omega, show j+(n-i)=n+(j-i) by omega] using h
