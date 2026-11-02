theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  classical
  obtain ⟨B, T, hB⟩ := boundedu
  let f : ℕ → ℤ × ℤ × ℤ × ℤ := fun n => (u n, u (n+1), u (n+2), u (n+3))
  have hf : Set.Finite (Set.range f) := by
    apply (Set.finite_Icc (B,B,B,B) (T,T,T,T)).subset
    rintro x ⟨n, rfl⟩
    exact ⟨⟨(hB n).1, (hB (n+1)).1, (hB (n+2)).1, (hB (n+3)).1⟩,
      (hB n).2, (hB (n+1)).2, (hB (n+2)).2, (hB (n+3)).2⟩
  have hc : ∃ i j, i < j ∧ f i = f j := by
    by_contra! h
    apply (Set.not_infinite.mpr hf) (Set.infinite_range_of_injective ?_)
    intro i j he
    exact le_antisymm (le_of_not_gt fun hij => h j i hij he.symm)
      (le_of_not_gt fun hij => h i j hij he)
  obtain ⟨i, j, hij, he⟩ := hc
  have hr (n : ℕ) := (hu (n+4) (by omega)).1
  simp [Nat.add_sub_assoc] at hr
  have hp (m : ℕ) : f (i+m) = f (j+m) := by
    induction m with
    | zero => simpa using he
    | succ m ih =>
      simp only [f, Prod.mk.injEq] at ih ⊢
      obtain ⟨h0,h1,h2,h3⟩ := ih
      have h4 : u (i+m+4) = u (j+m+4) := by
        apply Int.cast_injective (α := ℝ)
        rw [hr, hr, h0, h1, h2, h3]
      simpa [Nat.add_assoc] using And.intro h1 (And.intro h2 (And.intro h3 h4))
  refine ⟨i, j-i, by omega, ?_⟩
  intro n hn
  simpa only [f, show i+(n-i)=n by omega,
    show j+(n-i)=n+(j-i) by omega] using (congrArg Prod.fst (hp (n-i))).symm
