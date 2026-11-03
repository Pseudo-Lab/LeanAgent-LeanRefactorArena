lemma time_deriv_time_deriv_electricField_of_isExtrema {A : ElectromagneticPotential d}
    {𝓕 : FreeSpace}
    (hA : ContDiff ℝ ∞ A) (J : LorentzCurrentDensity d)
    (hJ : ContDiff ℝ ∞ J) (h : IsExtrema 𝓕 A J)
    (t : Time) (x : Space d) (i : Fin d) :
    ∂ₜ (∂ₜ (A.electricField 𝓕.c · x i)) t =
      𝓕.c ^ 2 * ∑ j, (∂[j] (∂[j] (A.electricField 𝓕.c t · i)) x) -
      𝓕.c ^ 2 / 𝓕.ε₀ * ∂[i] (J.chargeDensity 𝓕.c t ·) x -
      𝓕.c ^ 2 * 𝓕.μ₀ * ∂ₜ (J.currentDensity 𝓕.c · x i) t := by
  let E j := (A.electricField 𝓕.c t · j)
  let B j s := ∂[j] (A.magneticFieldMatrix 𝓕.c s · (j, i)) x
  let K := (J.currentDensity 𝓕.c · x i)
  have hEs (j) : ContDiff ℝ 2 (E j) :=
    electricField_apply_contDiff_space (i := j) (hA.of_le (right_eq_inf.mp rfl)) t
  have hEd (j k) := Space.deriv_differentiable (hEs j) k
  have hBt (j) : Differentiable ℝ (B j) :=
    Space.space_deriv_differentiable_time (i := j)
      (magneticFieldMatrix_contDiff A (hA.of_le (right_eq_inf.mp rfl)) (j, i)) x
  have hJt : Differentiable ℝ K :=
    LorentzCurrentDensity.currentDensity_apply_differentiable_time (hJ.differentiable (by simp)) x i
  have hρ : Differentiable ℝ (J.chargeDensity 𝓕.c t ·) := by
    apply LorentzCurrentDensity.chargeDensity_differentiable_space
    exact hJ.differentiable (by simp)
  have hdiv := congrArg (fun f => ∂[i] f x)
    (show (fun y => ∑ j, ∂[j] (E j) y) =
        (fun y => (1 / 𝓕.ε₀) * J.chargeDensity 𝓕.c t y) from by
      funext y
      change (∇ ⬝ (A.electricField 𝓕.c t)) y = _
      simpa only [div_eq_mul_inv, mul_one, one_mul, mul_comm] using
        ((isExtrema_iff_gauss_ampere_magneticFieldMatrix hA J hJ).mp h t y).1)
  conv at hdiv =>
    lhs
    rw [Space.deriv_eq_fderiv_basis,
      fderiv_fun_sum fun j _ => (hEd j j).differentiableAt]
  conv at hdiv =>
    rhs
    rw [Space.deriv_eq_fderiv_basis, fderiv_const_mul hρ.differentiableAt]
  simp only [FunLike.coe_sum, Finset.sum_apply, ContinuousLinearMap.smul_apply,
    smul_eq_mul, ← Space.deriv_eq_fderiv_basis] at hdiv
  have hcurl (j) : ∂ₜ (B j) t =
      ∂[j] (∂[j] (E i)) x - ∂[i] (∂[j] (E j)) x := by
    dsimp only [B, E]
    rw [Space.time_deriv_comm_space_deriv]
    · conv_lhs =>
        enter [2, y]
        rw [time_deriv_magneticFieldMatrix _ (hA.of_le ENat.LEInfty.out)]
      conv_lhs =>
        rw [Space.deriv_eq_fderiv_basis,
          fderiv_fun_sub (hEd _ _).differentiableAt (hEd _ _).differentiableAt]
        simp only [FunLike.coe_sub, Pi.sub_apply, ← Space.deriv_eq_fderiv_basis]
      congr 1
      rw [Space.deriv_commute _ (hEs _), Space.deriv_eq_fderiv_basis]
    · apply magneticFieldMatrix_contDiff
      exact hA.of_le (right_eq_inf.mp rfl)
  have he : ∂ₜ (A.electricField 𝓕.c · x i) =
      (fun s => 1 / (𝓕.μ₀ * 𝓕.ε₀) * ∑ j, B j s - 1 / 𝓕.ε₀ * K s) := by
    funext s
    rw [Time.deriv_euclid (electricField_differentiable_time
      (hA.of_le (right_eq_inf.mp rfl)) _),
      time_deriv_electricField_of_isExtrema hA J hJ h]
  have hc : 1 / (𝓕.μ₀ * 𝓕.ε₀) = 𝓕.c ^ 2 := by
    simp only [FreeSpace.c_sq, one_div, mul_inv_rev] <;> ring
  have hb : 1 / 𝓕.ε₀ = 𝓕.c ^ 2 * 𝓕.μ₀ := by
    rw [← hc]
    simp [mul_inv_rev, mul_assoc]
  conv_lhs =>
    rw [he, Time.deriv_eq,
      fderiv_fun_sub ((Differentiable.fun_sum fun j _ => hBt j).const_mul _).differentiableAt
        (hJt.const_mul _).differentiableAt,
      fderiv_const_mul (Differentiable.fun_sum fun j _ => hBt j).differentiableAt,
      fderiv_const_mul hJt.differentiableAt,
      fderiv_fun_sum fun j _ => (hBt j).differentiableAt]
    simp only [FunLike.coe_sub, Pi.sub_apply, ContinuousLinearMap.smul_apply,
      smul_eq_mul, FunLike.coe_sum, Finset.sum_apply, ← Time.deriv_eq]
    simp only [hcurl, Finset.sum_sub_distrib, mul_sub, hdiv, hc]
  rw [← mul_assoc, mul_one_div, hb]
