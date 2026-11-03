theorem putnam_2007_a1
    (P : (ℝ → ℝ) → Prop)
    (P_def : ∀ f, P f ↔ ∃ x y, f x = y ∧ f y = x ∧ deriv f x * deriv f y = 1)
    (α : ℝ) :
    P (fun t ↦ α * t ^ 2 + α * t + 1 / 24) ↔ α ∈ (({2 / 3, 3 / 2, (13 + √601) / 12, (13 - √601) / 12}) : Set ℝ ) := by
  have hd (x : ℝ) : deriv (fun t : ℝ => α * t ^ 2 + α * t + 1 / 24) x = 2 * α * x + α := by
    convert ((((hasDerivAt_pow 2 x).const_mul α).add ((hasDerivAt_id x).const_mul α)).add_const (1 / 24 : ℝ)).deriv using 1 <;> ring
  rw [P_def]
  simp only [hd, Set.mem_insert_iff, Set.mem_singleton_iff]
  have hsqrt : (√601) ^ 2 = (601 : ℝ) := Real.sq_sqrt (by norm_num)
  constructor
  · rintro ⟨x, y, hx, hy, hp⟩
    let u := 2 * α * x + α
    let v := 2 * α * y + α
    change u * v = 1 at hp
    have huv : u = v := by
      have hf : (u - v) * (u + v + 2) = 0 := by
        linear_combination 4 * α * (hx - hy)
      rcases mul_eq_zero.mp hf with h | h
      · exact sub_eq_zero.mp h
      · nlinarith only [h, hp, sq_nonneg (u - v)]
    rw [← huv] at hp
    dsimp [u, v] at hp huv
    simp only [← sub_eq_zero (a := α), ← mul_eq_zero]
    linear_combination (25 * α / 6 + 4 * α * x + 1 - α ^ 2) * (4 * α * hx - hp - 2 * huv) + 4 * hp - (α - 2 / 3) * (α - 3 / 2) / 144 * hsqrt
  · rintro (rfl | rfl | h | h)
    · exact ⟨1 / 4, 1 / 4, by norm_num⟩
    · exact ⟨-1 / 6, -1 / 6, by norm_num⟩
    all_goals
      have hq : 6 * α ^ 2 - 13 * α - 18 = 0 := by
        rw [h]
        linear_combination hsqrt / 24
      refine ⟨(-6 * α - 5) / 36, (-6 * α - 5) / 36, ?_, ?_, ?_⟩ <;>
        first | linear_combination (6 * α - 13) / 1296 * hq
              | linear_combination (6 * α ^ 2 - 13 * α + 18) / 324 * hq
