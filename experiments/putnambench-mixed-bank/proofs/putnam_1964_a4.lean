theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  obtain ⟨B, T, hbound⟩ := boundedu
  obtain ⟨a, b, hab, heq⟩ := Finite.exists_ne_map_eq_of_infinite
    (fun n (i : Fin 4) => (⟨_, hbound (n + i)⟩ : Icc B T))
  wlog h : a < b generalizing a b
  · exact this b a hab.symm heq.symm (by omega)
  have tail k : u (a + k) = u (b + k) := k.strongRecOn fun k ih => by
    by_cases hk : k < 4
    · simpa using congrFun heq ⟨k, hk⟩
    · apply @Int.cast_injective ℝ
      simp (disch := omega) only [(hu (a + k) (by omega)).1,
        (hu (b + k) (by omega)).1, Nat.add_sub_assoc, ih]
  refine ⟨a, b - a, Nat.sub_pos_of_lt h, fun n hn => ?_⟩
  convert (tail (n - a)).symm using 2 <;> omega
