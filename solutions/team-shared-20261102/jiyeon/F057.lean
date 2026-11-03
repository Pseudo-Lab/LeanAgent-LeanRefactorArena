theorem putnam_1970_b5
(ramp : ℤ → (ℝ → ℝ))
(ramp_def : ramp = fun (n : ℤ) => (fun (x : ℝ) => if x ≤ -n then (-n : ℝ) else (if -n < x ∧ x ≤ n then x else (n : ℝ))))
(F : ℝ → ℝ)
: Continuous F ↔ (∀ n : ℕ, Continuous ((ramp n) ∘ F))  := by
  have hr (n : ℕ) (x : ℝ) : ramp n x =
      if x ≤ -(n : ℝ) then -(n : ℝ) else
        if -(n : ℝ) < x ∧ x ≤ n then x else n := by simp [ramp_def]
  constructor
  · intro h n
    have he : ramp n = fun x : ℝ => min (max x (-(n : ℝ))) n := by
      funext x
      rw [hr]
      have hn := Nat.cast_nonneg (α := ℝ) n
      simp only [min_def, max_def]
      split_ifs <;> simp_all <;> linarith
    rw [he]
    exact ((continuous_id.max continuous_const).min continuous_const).comp h
  · intro h
    apply continuous_iff_continuousAt.mpr
    intro a
    rw [Metric.continuousAt_iff]
    intro ε hε
    obtain ⟨n, hn⟩ := exists_nat_gt (|F a| + ε)
    have hleft : -(n : ℝ) < F a := by linarith [neg_abs_le (F a)]
    have hright : F a ≤ (n : ℝ) := by linarith [le_abs_self (F a)]
    have ha : ramp n (F a) = F a := by
      rw [hr, if_neg (not_le.mpr hleft), if_pos ⟨hleft,hright⟩]
    obtain ⟨δ,hδ,hclose⟩ := Metric.continuousAt_iff.mp (h n).continuousAt ε hε
    refine ⟨δ,hδ,?_⟩
    intro x hx
    have hc : |ramp n (F x) - F a| < ε := by
      simpa only [Function.comp_apply, Real.dist_eq, ha] using hclose hx
    rw [Real.dist_eq]
    rw [hr] at hc
    split_ifs at hc with hlo hmid
    · have hl := (abs_lt.mp hc).1
      linarith [neg_abs_le (F a)]
    · exact hc
    · have hu := (abs_lt.mp hc).2
      linarith [le_abs_self (F a)]
