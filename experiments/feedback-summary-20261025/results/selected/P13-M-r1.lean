theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  classical
  obtain ⟨B, T, hb⟩ := boundedu
  let f : ℕ → Fin 4 → ℤ := fun n k => u (n+k)
  have hf : Set.Finite (Set.range f) := by
    apply (Set.finite_Icc (a := fun _ : Fin 4 => B) (b := fun _ => T)).subset
    rintro _ ⟨n, rfl⟩
    exact ⟨fun k => (hb (n+k)).1, fun k => (hb (n+k)).2⟩
  have hex : ∃ i j, i < j ∧ f i = f j := by
    by_contra! h
    have hinj : Function.Injective f := by
      intro i j e
      rcases lt_trichotomy i j with hlt | he | hgt
      · exact False.elim (h i j hlt e)
      · exact he
      · exact False.elim (h j i hgt e.symm)
    exact Set.not_infinite.mpr hf (Set.infinite_range_of_injective hinj)
  obtain ⟨i, j, hij, he⟩ := hex
  have hall : ∀ m, u (i+m) = u (j+m) := by
    intro m
    induction m using Nat.strong_induction_on with
    | h m ih =>
      by_cases hm : m < 4
      · exact congrFun he ⟨m, hm⟩
      · have hi := (hu (i+m) (by omega)).1
        have hj := (hu (j+m) (by omega)).1
        simp only [Nat.add_sub_assoc (show 1 ≤ m by omega), Nat.add_sub_assoc (show 2 ≤ m by omega), Nat.add_sub_assoc (show 3 ≤ m by omega), Nat.add_sub_assoc (show 4 ≤ m by omega)] at hi hj
        rw [ih (m-1) (by omega), ih (m-2) (by omega), ih (m-3) (by omega), ih (m-4) (by omega)] at hi
        exact_mod_cast hi.trans hj.symm
  refine ⟨i, j-i, by omega, ?_⟩
  intro n hn
  convert (hall (n-i)).symm using 1 <;> congr 1 <;> omega
