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
    simp only [Set.mem_Icc, Prod.le_def, f]
    exact ⟨⟨(hB _).1, (hB _).1, (hB _).1, (hB _).1⟩,
      ⟨(hB _).2, (hB _).2, (hB _).2, (hB _).2⟩⟩
  have hcol : ∃ i j, i < j ∧ f i = f j := by
    by_contra! h
    apply hf.not_infinite
    apply Set.infinite_range_of_injective
    intro i j he
    rcases lt_trichotomy i j with hij | hij | hij
    · exact False.elim (h i j hij he)
    · exact hij
    · exact False.elim (h j i hij he.symm)
  obtain ⟨i,j,hij,he⟩ := hcol
  have hr : ∀ n, (u (n+4) : ℝ) =
      ((u (n+3) + u (n+2) + u (n+1) * u n) : ℝ) /
      (u (n+3) * u (n+2) + u (n+1) + u n) := by
    intro n
    convert (hu (n+4) (by omega)).1 using 1 <;> congr 1 <;> omega
  have hall (m : ℕ) : f (i+m) = f (j+m) := by
    induction m with
    | zero => simpa using he
    | succ m ih =>
      simp only [f, Prod.mk.injEq] at ih ⊢
      obtain ⟨h0,h1,h2,h3⟩ := ih
      have h4 : u (i+m+4) = u (j+m+4) := by
        apply Int.cast_injective (α := ℝ)
        rw [hr, hr, h0, h1, h2, h3]
      simpa only [Nat.succ_eq_add_one, Nat.add_assoc, Nat.reduceAdd] using
        And.intro h1 (And.intro h2 (And.intro h3 h4))
  refine ⟨i,j-i,by omega,?_⟩
  intro n hn
  convert (congrArg Prod.fst (hall (n-i))).symm using 1 <;> congr 1 <;> omega
