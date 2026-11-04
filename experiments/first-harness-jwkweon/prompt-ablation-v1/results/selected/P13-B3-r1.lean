theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  classical
  obtain ⟨B, T, hB⟩ := boundedu
  let f := fun n => (u n, u (n+1), u (n+2), u (n+3))
  have hf : Set.Finite (Set.range f) := by
    apply Set.Finite.subset (Set.finite_mem_finset (Finset.Icc (B,B,B,B) (T,T,T,T)))
    rintro x ⟨n, rfl⟩
    simp only [Set.mem_setOf_eq, Finset.mem_Icc]
    exact ⟨⟨(hB n).1, (hB (n+1)).1, (hB (n+2)).1, (hB (n+3)).1⟩,
      ⟨(hB n).2, (hB (n+1)).2, (hB (n+2)).2, (hB (n+3)).2⟩⟩
  have hr : ∃ i j, i < j ∧ f i = f j := by
    by_contra! h
    apply Set.not_infinite.mpr hf
    apply Set.infinite_range_of_injective
    intro i j e
    exact le_antisymm (le_of_not_gt fun hji => h j i hji e.symm)
      (le_of_not_gt fun hij => h i j hij e)
  obtain ⟨i, j, hij, he⟩ := hr
  simp only [f, Prod.mk.injEq] at he
  have hall : ∀ m, u (i+m) = u (j+m) := by
    intro m
    induction m using Nat.strong_induction_on with
    | h m ih =>
      by_cases hm : m < 4
      · interval_cases m <;> first | exact he.1 | exact he.2.1 | exact he.2.2.1 | exact he.2.2.2
      · have hs (k : Fin 4) : u (i+m-(k.val+1)) = u (j+m-(k.val+1)) := by
          have hk := k.isLt
          simpa only [Nat.add_sub_assoc (by omega : k.val+1 ≤ m)] using ih (m-(k.val+1)) (by omega)
        have hi := (hu (i+m) (by omega)).1
        have hj := (hu (j+m) (by omega)).1
        rw [hs ⟨0, by decide⟩, hs ⟨1, by decide⟩, hs ⟨2, by decide⟩, hs ⟨3, by decide⟩] at hi
        exact_mod_cast hi.trans hj.symm
  refine ⟨i, j-i, by omega, ?_⟩
  intro n hn
  convert (hall (n-i)).symm using 1 <;> congr 1 <;> omega
