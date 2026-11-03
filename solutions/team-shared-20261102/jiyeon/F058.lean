theorem putnam_1968_a1
: 22/7 - Real.pi = ∫ x in (0)..1, x^4 * (1 - x)^4 / (1 + x^2) := by
  have hfun : (fun x : ℝ => x^4 * (1-x)^4 / (1+x^2)) =
      fun x => (x^6 - 4*x^5 + 5*x^4 - 4*x^2 + 4) - 4 * (1 / (1+x^2)) := by
    funext x
    field_simp
    <;> ring
  rw [hfun, intervalIntegral.integral_sub
    (Continuous.intervalIntegrable (by fun_prop) _ _) (Continuous.intervalIntegrable (by fun_prop (disch := intros; positivity)) _ _),
    intervalIntegral.integral_const_mul, integral_one_div_one_add_sq]
  norm_num [integral_id, mul_comm]
  ring
