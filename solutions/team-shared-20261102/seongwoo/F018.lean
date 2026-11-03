lemma fundamental_theorem_of_variational_calculus' {f : Y → V}
    (μ : Measure Y) [IsFiniteMeasureOnCompacts μ] [μ.IsOpenPosMeasure]
    [OpensMeasurableSpace Y]
    (hf : Continuous f) (hg : ∀ g, IsTestFunction g → ∫ x, ⟪f x, g x⟫_ℝ ∂μ = 0) :
    f = 0 := by
  ext x₀
  by_contra hx0
  let k := fun x => ⟪f x, f x₀⟫_ℝ
  have hself := (real_inner_self_pos (x := toL2 ℝ (f x₀))).mpr $
    mt (congrArg (fromL2 ℝ)) hx0
  have hc : Continuous k := Continuous.inner' _ _ hf continuous_const
  obtain ⟨δ, hδpos, hδ⟩ :=
    Metric.isOpen_iff.mp (isOpen_lt continuous_const hc) x₀ hself
  letI := hasContDiffBump_of_innerProductSpace Y
  let φ : ContDiffBump x₀ := ⟨δ / 2, δ, half_pos hδpos, half_lt_self hδpos⟩
  have hp := (φ.contDiff (n := 0)).continuous.mul hc
  have hn x : 0 ≤ φ x * k x := by
    by_cases hx : φ x = 0
    · simp only [hx, zero_mul, le_refl]
    · exact mul_nonneg φ.nonneg (hδ (φ.support_eq ▸ hx)).le
  apply ((integral_pos_iff_support_of_nonneg hn
    (hp.integrable_of_hasCompactSupport φ.hasCompactSupport.mul_right)).mpr $
    (isOpen_ne.preimage hp).measure_pos μ
      ⟨x₀, ne_of_gt $ mul_pos
        (φ.pos_of_mem_ball (Metric.mem_ball_self hδpos)) hself⟩).ne'
  simpa only [inner_smul_right'] using hg _ $
    IsTestFunction.smul_right ⟨φ.contDiff, φ.hasCompactSupport⟩ $
      contDiff_const (c := f x₀)
