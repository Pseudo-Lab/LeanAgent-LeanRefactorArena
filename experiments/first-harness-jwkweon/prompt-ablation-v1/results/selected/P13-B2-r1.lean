theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  classical
  obtain ⟨B, T, hB⟩ := boundedu
  let f : ℕ → Fin 4 → Set.Icc B T := fun n k => ⟨u (n+k), hB _⟩
  have hr : ∃ i j, i < j ∧ f i = f j := by
    obtain ⟨i,j,hne,he⟩ := Finite.exists_ne_map_eq_of_infinite f
    rcases lt_or_gt_of_ne hne with h | h
    · exact ⟨i,j,h,he⟩
    · exact ⟨j,i,h,he.symm⟩
  obtain ⟨i,j,hij,he⟩ := hr
  have H (m) : u (i+m) = u (j+m) := by
    induction m using Nat.strong_induction_on with
    | h m ih =>
      by_cases hm : m < 4
      · exact congrArg Subtype.val (congrFun he ⟨m, hm⟩)
      · have hs (k : ℕ) (hk : k < 4) : u (i+m-(k+1)) = u (j+m-(k+1)) := by
          simpa only [Nat.add_sub_assoc (by omega : k+1 ≤ m)] using ih (m-(k+1)) (by omega)
        apply Int.cast_injective (α := ℝ)
        rw [(hu (i+m) (by omega)).1, (hu (j+m) (by omega)).1]
        simp only [hs, Nat.reduceLT]
  refine ⟨i, j-i, by omega, ?_⟩
  intro n hn
  convert (H (n-i)).symm using 1 <;> congr 1 <;> omega
