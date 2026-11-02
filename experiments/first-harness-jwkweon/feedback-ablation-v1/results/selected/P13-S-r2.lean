theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  classical
  obtain ⟨B, T, hb⟩ := boundedu
  let f (n : ℕ) (k : Fin 4) : ℤ := u (n+k)
  have hf : (Set.range f).Finite := by
    apply (Set.finite_Icc (fun _ : Fin 4 => B) (fun _ => T)).subset
    rintro _ ⟨n, rfl⟩
    exact ⟨fun k => (hb _).1, fun k => (hb _).2⟩
  have hc : ∃ i j, i < j ∧ f i = f j := by
    by_contra! h
    apply hf.not_infinite
    apply Set.infinite_range_of_injective
    intro i j e
    rcases lt_trichotomy i j with hlt | he | hgt
    · exact False.elim (h i j hlt e)
    · exact he
    · exact False.elim (h j i hgt e.symm)
  obtain ⟨i, j, hij, he⟩ := hc
  have hall : ∀ m, u (i+m) = u (j+m) := by
    intro m
    induction m using Nat.strong_induction_on with
    | h m ih =>
      by_cases hm : m < 4
      · exact congrFun he ⟨m, hm⟩
      · have hp (k : ℕ) (hk : k < 4) : u (i+m-(k+1)) = u (j+m-(k+1)) := by
          simpa only [Nat.add_sub_assoc (by omega : k+1 ≤ m)] using
            ih (m-(k+1)) (by omega)
        apply Int.cast_injective (α := ℝ)
        rw [(hu (i+m) (by omega)).1, (hu (j+m) (by omega)).1,
          hp 0 (by decide), hp 1 (by decide), hp 2 (by decide), hp 3 (by decide)]
  refine ⟨i, j-i, by omega, ?_⟩
  intro n hn
  convert (hall (n-i)).symm using 1 <;> congr 1 <;> omega
