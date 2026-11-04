theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  classical
  obtain ⟨B, T, hB⟩ := boundedu
  let f : ℕ → Fin 4 → Set.Icc B T := fun n k => ⟨u (n+k), hB (n+k)⟩
  obtain ⟨i,j,hij,he⟩ : ∃ i j, i < j ∧ f i = f j := by
    obtain ⟨i,j,hne,he⟩ := Finite.exists_ne_map_eq_of_infinite f
    rcases lt_or_gt_of_ne hne with hij | hij
    · exact ⟨i,j,hij,he⟩
    · exact ⟨j,i,hij,he.symm⟩
  have hall : ∀ m, u (i+m) = u (j+m) := by
    intro m
    induction m using Nat.strong_induction_on with
    | h m ih =>
      by_cases hm : m < 4
      · exact congrArg Subtype.val (congrFun he ⟨m,hm⟩)
      · have hp : ∀ k, 0 < k → k ≤ 4 → u (i+m-k) = u (j+m-k) := by
          intro k hk hk4
          simpa only [Nat.add_sub_assoc (by omega : k ≤ m)] using ih (m-k) (by omega)
        have hr : (u (i+m) : ℝ) = (u (j+m) : ℝ) := by
          rw [(hu (i+m) (by omega)).1, (hu (j+m) (by omega)).1,
            hp 1 (by decide) (by decide), hp 2 (by decide) (by decide),
            hp 3 (by decide) (by decide), hp 4 (by decide) (by decide)]
        exact_mod_cast hr
  refine ⟨i, j-i, by omega, ?_⟩
  intro n hn
  convert (hall (n-i)).symm using 1 <;> congr 1 <;> omega
