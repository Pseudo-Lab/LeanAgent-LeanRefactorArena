theorem putnam_1988_a2
    (f : ℝ → ℝ)
    (hf : f = fun x ↦ Real.exp (x ^ 2)) :
    ((True) : Prop ) ↔
    (∃ a b : ℝ,
      a < b ∧
      ∃ g : ℝ → ℝ,
        (∃ x ∈ Ioo a b, g x ≠ 0) ∧
        DifferentiableOn ℝ g (Ioo a b) ∧
        ∀ x ∈ Ioo a b, deriv (fun y ↦ f y * g y) x = (deriv f x) * (deriv g x))  := by
  subst f
  simp only [true_iff]
  let g : ℝ → ℝ := fun x => Real.exp x * Real.sqrt (2*x-1)
  have hg (x : ℝ) (hx : x ∈ Ioo (1:ℝ) 2) :
      HasDerivAt g (Real.exp x * Real.sqrt (2*x-1) + Real.exp x / Real.sqrt (2*x-1)) x := by
    have hs : Real.sqrt (2*x-1) ≠ 0 := (Real.sqrt_pos.mpr (by linarith [hx.1])).ne'
    have hlin : HasDerivAt (fun t : ℝ => 2*t-1) 2 x := by
      simpa using ((hasDerivAt_id x).const_mul 2).sub_const 1
    convert (Real.hasDerivAt_exp x).mul (hlin.sqrt (by linarith [hx.1])) using 1 <;>
      dsimp [g] <;> field_simp [hs] <;> ring
  refine ⟨1,2,by norm_num,g,?_,?_,?_⟩
  · refine ⟨3/2,by norm_num,?_⟩
    dsimp [g]
    positivity
  · intro x hx
    exact (hg x hx).differentiableAt.differentiableWithinAt
  · intro x hx
    have hs : 0 < Real.sqrt (2*x-1) := Real.sqrt_pos.mpr (by linarith [hx.1])
    have hf := (hasDerivAt_pow 2 x).exp
    change deriv ((fun y : ℝ => Real.exp (y^2)) * g) x = _
    rw [(hf.mul (hg x hx)).deriv, hf.deriv, (hg x hx).deriv]
    dsimp [g]
    simp only [pow_one]
    field_simp [hs.ne']
    rw [Real.sq_sqrt (show 0 ≤ x*2-1 by linarith [hx.1])]
    ring
