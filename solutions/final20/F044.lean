lemma step1_double :
    2 * ∫ α in (0:ℝ)..1, α * extremalSelfConv α
      = ∫ u in (-(1:ℝ)/2)..(1/2),
          extremalTest u * ∫ v in (-(1:ℝ)/2)..(1/2), |u - v| * extremalTest v := by
  let a : ℝ := -(1:ℝ)/2
  let b : ℝ := (1:ℝ)/2
  have hab : a ≤ b := by norm_num [a, b]
  have hneg (f : ℝ → ℝ) : (∫ x in a..b, f (-x)) = ∫ x in a..b, f x := by
    simpa only [a, b, neg_div, neg_neg] using
      intervalIntegral.integral_comp_neg f (a := a) (b := b)
  have hrect : IntegrableOn
      (Function.uncurry (fun α t => α * (extremalTest t * extremalTest (α - t))))
      (Set.uIoc (0:ℝ) 1 ×ˢ Set.uIoc a b) volume := by
    apply IntegrableOn.of_bound _
      (measurable_fst.mul ((extremalTest_measurable.comp measurable_snd).mul
        (extremalTest_measurable.comp (measurable_fst.sub measurable_snd)))).aestronglyMeasurable _
    · filter_upwards [ae_restrict_mem (measurableSet_uIoc.prod measurableSet_uIoc)] with p hp
      have hp1 := hp.1
      rw [Set.uIoc_of_le (by norm_num : (0:ℝ) ≤ 1)] at hp1
      change ‖p.1 * (extremalTest p.2 * extremalTest (p.1 - p.2))‖ ≤ _
      rw [norm_mul, norm_mul]
      exact mul_le_mul (by rw [Real.norm_of_nonneg hp1.1.le]; exact hp1.2)
        (mul_le_mul (extremalTest_abs_le _) (extremalTest_abs_le _) (norm_nonneg _)
          ((abs_nonneg _).trans (extremalTest_abs_le 0)))
        (mul_nonneg (norm_nonneg _) (norm_nonneg _)) zero_le_one
    · exact (measure_mono (Set.prod_mono Set.uIoc_subset_uIcc Set.uIoc_subset_uIcc)).trans_lt
        (isCompact_uIcc.prod isCompact_uIcc).measure_lt_top
  have hM : (∫ α in (0:ℝ)..1, α * extremalSelfConv α) =
      ∫ t in a..b, extremalTest t * ∫ v in a..b, max (t - v) 0 * extremalTest v := by
    calc
      _ = ∫ α in (0:ℝ)..1, ∫ t in a..b,
          α * (extremalTest t * extremalTest (α - t)) := by
        simp only [extremalSelfConv_eq_interval, intervalIntegral.integral_const_mul, a, b]
      _ = ∫ t in a..b, ∫ α in (0:ℝ)..1,
          α * (extremalTest t * extremalTest (α - t)) :=
        MeasureTheory.intervalIntegral_intervalIntegral_swap hrect
      _ = _ := by
        apply intervalIntegral.integral_congr
        intro t ht
        rw [Set.uIcc_of_le hab, Set.mem_Icc] at ht
        have htabs : |t| ≤ 1/2 := by simpa only [abs_le, a, b, neg_div] using ht
        simp only [mul_left_comm _ (extremalTest t), intervalIntegral.integral_const_mul]
        rw [inner_reduce htabs]
        congr 1
        simpa only [extremalTest_even, sub_neg_eq_add, add_comm] using
          hneg (fun v => max (t - v) 0 * extremalTest v)
  have hsymm : (∫ t in a..b, extremalTest t * ∫ v in a..b, max (t - v) 0 * extremalTest v) =
      ∫ t in a..b, extremalTest t * ∫ v in a..b, max (v - t) 0 * extremalTest v := by
    rw [← hneg (fun t => extremalTest t * ∫ v in a..b, max (t - v) 0 * extremalTest v)]
    congr 1
    funext t
    simp only [extremalTest_even]
    rw [← hneg (fun v => max (-t - v) 0 * extremalTest v)]
    simp only [extremalTest_even, neg_sub_neg]
  rw [hM, two_mul]
  nth_rewrite 2 [hsymm]
  rw [← intervalIntegral.integral_add
    (outer_intervalIntegrable (fun t v => max (t - v) 0)
      ((continuous_fst.sub continuous_snd).max continuous_const))
    (outer_intervalIntegrable (fun t v => max (v - t) 0)
      ((continuous_snd.sub continuous_fst).max continuous_const))]
  congr 1
  funext t
  rw [← mul_add, ← intervalIntegral.integral_add
    (maxSubTest_intervalIntegrable t a b)
    (by simpa only [sub_eq_add_neg] using maxTest_intervalIntegrable (-t) a b)]
  simp_rw [← add_mul, ← max_zero_add_max_neg_zero_eq_abs_self, neg_sub]
  rfl
