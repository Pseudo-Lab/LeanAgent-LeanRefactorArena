theorem putnam_1968_a1
: 22/7 - Real.pi = ∫ x in (0)..1, x^4 * (1 - x)^4 / (1 + x^2) := by
  symm
  calc
    _ = ∫ x in 0..1, (x^6 - 4*x^5) - (4*x^2 - 5*x^4) - (4 * (1 / (1 + x^2)) - 4) := by
      congr 1
      ext x
      field_simp (disch := positivity) <;> ring
    _ = 22/7 - Real.pi := by
      simp (disch := repeat' first | apply IntervalIntegrable.sub | apply IntervalIntegrable.const_mul | apply intervalIntegral.intervalIntegrable_pow | apply intervalIntegral.intervalIntegrable_const | apply intervalIntegral.intervalIntegrable_one_div_one_add_sq) only
        [intervalIntegral.integral_sub, intervalIntegral.integral_const_mul, integral_pow,
         intervalIntegral.integral_const, integral_one_div_one_add_sq,
         Real.arctan_one, Real.arctan_zero, smul_eq_mul]
      ring
