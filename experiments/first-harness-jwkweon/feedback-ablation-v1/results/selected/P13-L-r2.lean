theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  obtain ⟨B, T, hB⟩ := boundedu
  let f : ℕ → Fin 4 → ℤ := fun n k => u (n+k)
  have hf : Set.Finite (Set.range f) := by
    apply (Set.finite_Icc (fun _ : Fin 4 => B) (fun _ => T)).subset
    rintro x ⟨n, rfl⟩
    exact ⟨fun k => (hB _).1, fun k => (hB _).2⟩
  obtain ⟨i,j,hij,he⟩ := hf.exists_lt_map_eq_of_forall_mem (fun n : ℕ => Set.mem_range_self n)
  have hs : ∀ m, u (i+m) = u (j+m) := by
    intro m
    induction m using Nat.strong_induction_on with
    | h m ih =>
      by_cases hm : m < 4
      · exact congrFun he ⟨m, hm⟩
      · have hk (k : ℕ) (hk : 0 < k ∧ k ≤ 4) : u (i+m-k) = u (j+m-k) := by
          simpa only [Nat.add_sub_assoc (by omega : k ≤ m)] using ih (m-k) (by omega)
        apply Int.cast_injective (α := ℝ)
        rw [(hu (i+m) (by omega)).1, (hu (j+m) (by omega)).1,
          hk 1 (by decide), hk 2 (by decide), hk 3 (by decide), hk 4 (by decide)]
  refine ⟨i, j-i, by omega, ?_⟩
  intro n hn
  convert (hs (n-i)).symm using 1 <;> congr 1 <;> omega
