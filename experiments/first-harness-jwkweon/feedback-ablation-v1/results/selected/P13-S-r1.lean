theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  classical
  obtain ⟨B, T, hB⟩ := boundedu
  let f : ℕ → ℤ × ℤ × ℤ × ℤ := fun n => (u n, u (n+1), u (n+2), u (n+3))
  have hf : Set.Finite (Set.range f) := by
    apply Set.Finite.subset (Set.finite_mem_finset (Finset.Icc (B,B,B,B) (T,T,T,T)))
    rintro x ⟨n, rfl⟩
    simp only [Finset.mem_Icc, Prod.le_def]
    exact ⟨⟨(hB _).1, (hB _).1, (hB _).1, (hB _).1⟩,
      ⟨(hB _).2, (hB _).2, (hB _).2, (hB _).2⟩⟩
  have hp : ∃ i j, i < j ∧ f i = f j := by
    by_contra! h
    apply Set.not_infinite.mpr hf
    apply Set.infinite_range_of_injective
    intro i j he
    rcases lt_trichotomy i j with hij | hij | hij
    · exact False.elim (h i j hij he)
    · exact hij
    · exact False.elim (h j i hij he.symm)
  have step (a b : ℕ) (h : f a = f b) : f (a+1) = f (b+1) := by
    simp only [f, Prod.mk.injEq] at h
    have ha := (hu (a+4) (by omega)).1
    have hb := (hu (b+4) (by omega)).1
    simp [Nat.add_sub_assoc] at ha hb
    simp only [h.1, h.2.1, h.2.2.1, h.2.2.2] at ha
    simp only [f, Prod.mk.injEq, Nat.add_assoc]
    exact ⟨h.2.1, h.2.2.1, h.2.2.2, Int.cast_injective (ha.trans hb.symm)⟩
  obtain ⟨i,j,hij,he⟩ := hp
  have hall (m : ℕ) : f (i+m) = f (j+m) := by
    induction m with
    | zero => simpa using he
    | succ m ih => simpa [Nat.add_assoc] using step (i+m) (j+m) ih
  refine ⟨i, j-i, by omega, ?_⟩
  intro n hn
  simpa only [f, show i+(n-i) = n by omega, show j+(n-i) = n+(j-i) by omega] using congrArg Prod.fst (hall (n-i)).symm
