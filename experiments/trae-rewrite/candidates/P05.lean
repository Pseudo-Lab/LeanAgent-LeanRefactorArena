lemma time_deriv_time_deriv_electricField_of_isExtrema {A : ElectromagneticPotential d}
    {𝓕 : FreeSpace}
    (hA : ContDiff ℝ ∞ A) (J : LorentzCurrentDensity d)
    (hJ : ContDiff ℝ ∞ J) (h : IsExtrema 𝓕 A J)
    (t : Time) (x : Space d) (i : Fin d) :
    ∂ₜ (∂ₜ (A.electricField 𝓕.c · x i)) t =
      𝓕.c ^ 2 * ∑ j, (∂[j] (∂[j] (A.electricField 𝓕.c t · i)) x) -
      𝓕.c ^ 2 / 𝓕.ε₀ * ∂[i] (J.chargeDensity 𝓕.c t ·) x -
      𝓕.c ^ 2 * 𝓕.μ₀ * ∂ₜ (J.currentDensity 𝓕.c · x i) t := by
  have hA₂ : ContDiff ℝ 2 A := hA.of_le ENat.LEInfty.out
  have hA₃ : ContDiff ℝ 3 A := hA.of_le ENat.LEInfty.out
  have hEs := fun j => electricField_apply_contDiff_space (n := 2) (c := 𝓕.c) (i := j) hA₃ t
  have hEd := fun j => Space.deriv_differentiable (hEs j)
  have hBs := magneticFieldMatrix_contDiff (n := 2) (c := 𝓕.c) A hA₃
  have hJd := hJ.differentiable (WithTop.coe_ne_zero.2 ENat.top_ne_zero)
  have hg := congrArg (∂[i] · x)
    (funext fun x => ((isExtrema_iff_gauss_ampere_magneticFieldMatrix hA J hJ).mp h t x).1)
  unfold Space.div at hg
  rw [Space.deriv_eq_fderiv_basis,
    fderiv_fun_sum (fun j _ => (hEd j j).differentiableAt)] at hg
  conv at hg =>
    rhs
    rw [Space.deriv_eq_fderiv_basis]
    simp only [div_eq_inv_mul]
    rw [fderiv_const_mul ((LorentzCurrentDensity.chargeDensity_differentiable_space hJd t) x)]
  simp only [_root_.sum_apply, _root_.smul_apply, smul_eq_mul,
    ← Space.deriv_eq_fderiv_basis] at hg
  conv_lhs =>
    enter [1, t]
    rw [Time.deriv_euclid (electricField_differentiable_time hA₂ _),
      time_deriv_electricField_of_isExtrema hA J hJ h]
  rw [Time.deriv_eq, ((((HasFDerivAt.fun_sum fun j _ => (Space.space_deriv_differentiable_time (i := j) (hBs (j, i)) x t).hasFDerivAt).const_mul _).fun_sub
    ((LorentzCurrentDensity.currentDensity_apply_differentiable_time (c := 𝓕.c) hJd x i t).hasFDerivAt.const_mul _))).fderiv]
  simp only [ContinuousLinearMap.sub_apply, ContinuousLinearMap.smul_apply, ContinuousLinearMap.sum_apply,
    smul_eq_mul, ← Time.deriv_eq]
  simp only [Space.time_deriv_comm_space_deriv (hBs _), time_deriv_magneticFieldMatrix _ hA₂,
    fun j => Space.fun_deriv_sub (u := j) _ _ (hEd i j) (hEd j i), Finset.sum_sub_distrib,
    fun j => congrFun (Space.deriv_commute (u := j) (v := i) _ (hEs j)) x]
  rw [hg, FreeSpace.c_sq, mul_comm 𝓕.ε₀ 𝓕.μ₀]
  simp only [div_eq_mul_inv, mul_inv_rev, one_mul, mul_sub, mul_assoc, inv_mul_cancel_left₀ 𝓕.μ₀_ne_zero]
