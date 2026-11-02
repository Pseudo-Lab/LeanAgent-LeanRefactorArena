theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  classical
  obtain ⟨B, T, hb⟩ := boundedu
  let f : ℕ → Fin 4 → Set.Icc B T := fun n k => ⟨u (n+k), hb _⟩
  have hc : ∃ i j, i < j ∧ f i = f j := by
    obtain ⟨i, j, hne, he⟩ := Finite.exists_ne_map_eq_of_infinite f
    rcases lt_or_gt_of_ne hne with h | h
    · exact ⟨i, j, h, he⟩
    · exact ⟨j, i, h, he.symm⟩
  obtain ⟨i, j, hij, he⟩ := hc
  have hp : ∀ m, u (i+m) = u (j+m) := by
    intro m
    induction m using Nat.strong_induction_on with
    | h m ih =>
      by_cases hm : m < 4
      · exact congrArg Subtype.val (congrFun he ⟨m, hm⟩)
      · have hm : 4 ≤ m := by omega
        have hi := (hu (i+m) (by omega)).1
        have hj := (hu (j+m) (by omega)).1
        have hs (k : Fin 4) : u (i+m-(k.val+1)) = u (j+m-(k.val+1)) := by
          have hk := k.isLt
          simpa only [Nat.add_sub_assoc (by omega : k.val+1 ≤ m)] using ih (m-(k.val+1)) (by omega)
        rw [hs ⟨0, by decide⟩, hs ⟨1, by decide⟩, hs ⟨2, by decide⟩, hs ⟨3, by decide⟩] at hi
        exact_mod_cast hi.trans hj.symm
  refine ⟨i, j-i, by omega, ?_⟩
  intro n hn
  convert (hp (n-i)).symm using 1 <;> congr 1 <;> omega
