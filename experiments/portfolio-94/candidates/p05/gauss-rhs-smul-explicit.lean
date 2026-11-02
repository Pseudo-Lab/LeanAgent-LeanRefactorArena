lemma time_deriv_time_deriv_electricField_of_isExtrema {A : ElectromagneticPotential d}
    {𝓕 : FreeSpace}
    (hA : ContDiff ℝ ∞ A) (J : LorentzCurrentDensity d)
    (hJ : ContDiff ℝ ∞ J) (h : IsExtrema 𝓕 A J)
    (t : Time) (x : Space d) (i : Fin d) :
    ∂ₜ (∂ₜ (A.electricField 𝓕.c · x i)) t =
      𝓕.c ^ 2 * ∑ j, (∂[j] (∂[j] (A.electricField 𝓕.c t · i)) x) -
      𝓕.c ^ 2 / 𝓕.ε₀ * ∂[i] (J.chargeDensity 𝓕.c t ·) x -
      𝓕.c ^ 2 * 𝓕.μ₀ * ∂ₜ (J.currentDensity 𝓕.c · x i) t := by
  let k := 1 / (𝓕.μ₀ * 𝓕.ε₀)
  have hA₂ : ContDiff ℝ 2 A := hA.of_le (by decide)
  have hEs := fun j => electricField_apply_contDiff_space (n := 2) (c := 𝓕.c) (i := j) (hA.of_le (by decide)) t
  have hEd := fun j => Space.deriv_differentiable (hEs j)
  have hBs := magneticFieldMatrix_contDiff (n := 2) (c := 𝓕.c) A (hA.of_le (by decide))
  have hBt := fun j => Space.space_deriv_differentiable_time (i := j) (hBs (j, i)) x
  have hSum := Differentiable.fun_sum (u := Finset.univ) fun j _ => hBt j
  have hJd := hJ.differentiable (by decide)
  have hJt := LorentzCurrentDensity.currentDensity_apply_differentiable_time (c := 𝓕.c) hJd x i
  have hg := congrArg (∂[i] · x)
    (funext fun x => ((isExtrema_iff_gauss_ampere_magneticFieldMatrix hA J hJ).mp h t x).1)
  change ∂[i] (fun x => ∑ j : Fin d, _) x = _ at hg
  rw [Space.deriv_eq_fderiv_basis,
    fderiv_fun_sum (fun j _ => (hEd j j).differentiableAt)] at hg
  conv at hg =>
    rhs
    simp only [div_eq_inv_mul, ← smul_eq_mul]
    erw [Space.deriv_const_smul (𝓕.ε₀⁻¹) (LorentzCurrentDensity.chargeDensity_differentiable_space (c := 𝓕.c) hJd t)]
  simp only [_root_.sum_apply, _root_.smul_apply, smul_eq_mul,
    ← Space.deriv_eq_fderiv_basis] at hg
  conv_lhs =>
    enter [1, t]
    rw [Time.deriv_euclid (electricField_differentiable_time hA₂ _),
      time_deriv_electricField_of_isExtrema hA J hJ h]
  rw [Time.deriv_eq, fderiv_fun_sub (hSum.differentiableAt.const_mul k)
    (hJt.differentiableAt.const_mul _), fderiv_const_mul hSum.differentiableAt,
    fderiv_const_mul hJt.differentiableAt]
  simp only [FunLike.coe_sub, Pi.sub_apply, _root_.smul_apply, smul_eq_mul, ← Time.deriv_eq]
  rw [Time.deriv_fun_sum _ _ fun i _ => (hBt i).differentiableAt]
  simp only [Space.time_deriv_comm_space_deriv (hBs _), time_deriv_magneticFieldMatrix _ hA₂]
  have hs j := Space.fun_deriv_sub (u := j) _ _ (hEd i j) (hEd j i)
  simp only [hs, Finset.sum_sub_distrib]
  have hc j := congrFun (Space.deriv_commute (u := j) (v := i)
    _ (hEs j)) x
  simp only [hc]
  rw [hg, FreeSpace.c_sq]
  simp only [k, div_eq_mul_inv, mul_inv_rev, mul_one, mul_sub, mul_assoc, mul_left_comm, mul_comm]
  rw [mul_left_comm 𝓕.μ₀, mul_inv_cancel_left₀ 𝓕.μ₀_ne_zero]
