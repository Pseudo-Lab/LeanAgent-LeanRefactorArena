theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  obtain ⟨B, T, hB⟩ := boundedu
  let f n (k : Fin 4) := u (n+k)
  have hf : (Set.range f).Finite := by
    apply (Set.finite_Icc (fun _ : Fin 4 => B) (fun _ => T)).subset
    rintro _ ⟨n, rfl⟩
    exact ⟨fun k => (hB _).1, fun k => (hB _).2⟩
  have hr : ∃ i j, i < j ∧ f i = f j := by
    by_contra! h
    apply hf.not_infinite
    apply Set.infinite_range_of_injective
    intro i j he
    by_contra hn
    rcases lt_or_gt_of_ne hn with hij | hij
    · exact h i j hij he
    · exact h j i hij he.symm
  obtain ⟨i,j,hij,he⟩ := hr
  have hp : ∀ m, u (i+m) = u (j+m) := by
    intro m
    induction m using Nat.strong_induction_on with
    | h m ih =>
      by_cases hm : m < 4
      · exact congrFun he ⟨m,hm⟩
      · have hi := (hu (i+m) (by omega)).1
        have hj := (hu (j+m) (by omega)).1
        simp (disch := omega) only [Nat.add_sub_assoc] at hi hj
        apply Int.cast_injective (α := ℝ)
        rw [hi, hj, ih (m-1) (by omega), ih (m-2) (by omega), ih (m-3) (by omega), ih (m-4) (by omega)]
  refine ⟨i,j-i,by omega,?_⟩
  intro n hn
  convert (hp (n-i)).symm using 1 <;> congr 1 <;> omega
