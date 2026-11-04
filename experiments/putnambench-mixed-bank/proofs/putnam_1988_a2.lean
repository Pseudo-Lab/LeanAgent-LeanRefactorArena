theorem putnam_1988_a2
    (f : ℝ → ℝ)
    (hf : f = fun x ↦ Real.exp (x ^ 2)) :
    ((True) : Prop ) ↔
    (∃ a b : ℝ,
      a < b ∧
      ∃ g : ℝ → ℝ,
        (∃ x ∈ Ioo a b, g x ≠ 0) ∧
        DifferentiableOn ℝ g (Ioo a b) ∧
        ∀ x ∈ Ioo a b, deriv (fun y ↦ f y * g y) x = (deriv f x) * (deriv g x)) := by
  subst f
  let g : ℝ → ℝ := fun x => Real.exp (x + Real.log (2 * x - 1) / 2)
  have hG (x : ℝ) (hx : 1 < x) : HasDerivAt g _ x :=
    ((hasDerivAt_id x).add
      (((((hasDerivAt_id x).const_mul 2).sub_const 1).log
        (by linarith : 2 * x - 1 ≠ 0)).div_const 2)).exp
  rw [true_iff]
  refine ⟨1, 2, by norm_num, g, ?_, ?_, ?_⟩
  · exact ⟨3 / 2, by norm_num, Real.exp_ne_zero _⟩
  · exact fun x hx => (hG x hx.1).differentiableAt.differentiableWithinAt
  · intro x hx
    have hF := (hasDerivAt_pow 2 x).exp
    change deriv ((fun y : ℝ => Real.exp (y ^ 2)) * g) x = _
    rw [(hF.mul (hG x hx.1)).deriv, hF.deriv, (hG x hx.1).deriv]
    simp only [Pi.add_apply, id_eq]
    linear_combination -Real.exp (x ^ 2) * g x *
      mul_inv_cancel₀ (show 2 * x - 1 ≠ 0 by linarith [hx.1])
