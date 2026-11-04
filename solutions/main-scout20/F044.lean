lemma step1_double :
    2 * ∫ α in (0:ℝ)..1, α * extremalSelfConv α
      = ∫ u in (-(1:ℝ)/2)..(1/2),
          extremalTest u * ∫ v in (-(1:ℝ)/2)..(1/2), |u - v| * extremalTest v := by
  set a : ℝ := -(1:ℝ)/2 with ha
  set b : ℝ := (1:ℝ)/2 with hb
  have hab : a ≤ b := by norm_num [ha, hb]
  have hneg (f : ℝ → ℝ) : (∫ x in a..b, f (-x)) = ∫ x in a..b, f x := by
    simpa only [ha, hb, neg_div, neg_neg] using
      (intervalIntegral.integral_comp_neg f (a := a) (b := b))
  set C : ℝ := (Real.sqrt 2 * Real.sin (1 / Real.sqrt 2))⁻¹
  have hIntegrRect : IntegrableOn (Function.uncurry (fun α t => α * (extremalTest t * extremalTest (α - t))))
      (Set.uIoc (0:ℝ) 1 ×ˢ Set.uIoc a b) volume := by
    apply MeasureTheory.IntegrableOn.of_bound _
      (measurable_fst.mul ((extremalTest_measurable.comp measurable_snd).mul
        (extremalTest_measurable.comp (measurable_fst.sub measurable_snd)))).aestronglyMeasurable (1 * (C * C))
    · filter_upwards [MeasureTheory.ae_restrict_mem
        (measurableSet_uIoc.prod measurableSet_uIoc)] with p hp
      have hpα := hp.1
      rw [Set.uIoc_of_le zero_le_one] at hpα
      simp only [Function.comp_apply, Pi.mul_apply, Pi.sub_apply,
        Real.norm_eq_abs, abs_mul]
      exact mul_le_mul
        (by rw [abs_of_pos hpα.1]; exact hpα.2 : |p.1| ≤ (1:ℝ))
        (mul_le_mul (extremalTest_abs_le _) (extremalTest_abs_le _) (abs_nonneg _)
          ((abs_nonneg (extremalTest 0)).trans (extremalTest_abs_le 0)))
        (mul_nonneg (abs_nonneg _) (abs_nonneg _)) zero_le_one
    · exact lt_of_le_of_lt
        (measure_mono (Set.prod_mono Set.uIoc_subset_uIcc Set.uIoc_subset_uIcc))
        (isCompact_uIcc.prod isCompact_uIcc).measure_lt_top
  have hM : (∫ α in (0:ℝ)..1, α * extremalSelfConv α)
      = ∫ t in a..b, extremalTest t * ∫ v in a..b, max (t - v) 0 * extremalTest v := by
    refine Eq.trans ?_ ((MeasureTheory.intervalIntegral_intervalIntegral_swap hIntegrRect).trans ?_)
    · simp_rw [extremalSelfConv_eq_interval, ← ha, ← hb, intervalIntegral.integral_const_mul]
    · apply intervalIntegral.integral_congr
      intro t ht
      rw [Set.uIcc_of_le hab, ha, hb, Set.mem_Icc] at ht
      simp_rw [mul_left_comm _ (extremalTest t), intervalIntegral.integral_const_mul]
      rw [inner_reduce (by simpa only [abs_le, neg_div] using ht)]
      congr 1
      simpa only [extremalTest_even, sub_neg_eq_add, add_comm, ha, hb] using
        hneg (fun v => max (t - v) 0 * extremalTest v)
  have hrefl (t : ℝ) := (hneg (fun v => max (-t - v) 0 * extremalTest v)).symm
  simp only [extremalTest_even, sub_neg_eq_add, neg_add_eq_sub] at hrefl
  rw [hM, two_mul]
  nth_rewrite 2 [← hneg (fun t => extremalTest t * ∫ v in a..b, max (t - v) 0 * extremalTest v)]
  simp only [extremalTest_even, hrefl]
  rw [← intervalIntegral.integral_add
    (outer_intervalIntegrable (fun t v => max (t - v) 0)
      ((continuous_fst.sub continuous_snd).max continuous_const))
    (outer_intervalIntegrable (fun t v => max (v - t) 0)
      ((continuous_snd.sub continuous_fst).max continuous_const))]
  apply intervalIntegral.integral_congr
  intro t _
  simp only
  rw [← mul_add, ← intervalIntegral.integral_add
    (maxSubTest_intervalIntegrable t a b) (by
      simpa only [sub_eq_add_neg] using maxTest_intervalIntegrable (-t) a b)]
  simp_rw [← add_mul, ← max_zero_add_max_neg_zero_eq_abs_self, neg_sub]
