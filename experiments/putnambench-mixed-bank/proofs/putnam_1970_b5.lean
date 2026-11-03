theorem putnam_1970_b5
(ramp : ℤ → (ℝ → ℝ))
(ramp_def : ramp = fun (n : ℤ) => (fun (x : ℝ) => if x ≤ -n then (-n : ℝ) else (if -n < x ∧ x ≤ n then x else (n : ℝ))))
(F : ℝ → ℝ)
: Continuous F ↔ (∀ n : ℕ, Continuous ((ramp n) ∘ F)) := by
  rw [ramp_def]
  simp only [Function.comp_def, Int.cast_natCast]
  constructor
  · intro h n
    have hn : -(n : ℝ) ≤ n := by linarith [Nat.cast_nonneg (α := ℝ) n]
    convert (h.max continuous_const).min continuous_const using 1
    funext x
    split_ifs with h₁ h₂
    · rw [max_eq_right h₁, min_eq_left hn]
    · rw [max_eq_left h₂.1.le, min_eq_left h₂.2]
    · rw [max_eq_left (le_of_not_ge h₁), min_eq_right (le_of_not_ge (not_and.mp h₂ (lt_of_not_ge h₁)))]
  · intro h
    simp only [continuous_iff_continuousAt, Metric.continuousAt_iff, Real.dist_eq] at h ⊢
    intro x ε hε
    obtain ⟨n, hn⟩ := exists_nat_gt (|F x| + ε)
    have h₀ := abs_lt.mp (lt_sub_iff_add_lt.mpr hn)
    have h₂ : -(n : ℝ) < F x ∧ F x ≤ n := by constructor <;> linarith [h₀.1, h₀.2]
    obtain ⟨δ, hδ, hd⟩ := h n x ε hε
    refine ⟨δ, hδ, fun {y} hy => ?_⟩
    have hh := hd hy
    simp only [if_neg (not_le.mpr h₂.1), if_pos h₂, abs_lt] at hh ⊢
    split_ifs at hh with h₁ h₂
    · linarith [hh.1, h₀.1]
    · exact hh
    · linarith [hh.2, h₀.2]
