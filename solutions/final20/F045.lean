theorem holomorphic_constant_rank
    {n m r : ℕ}
    {F : ComplexEuclidean n → ComplexEuclidean m}
    {a : ComplexEuclidean n}
    (hF : AnalyticAt ℂ F a)
    (hrn : r ≤ n)
    (hrm : r ≤ m)
    (hconst : ∀ᶠ x in nhds a, complexRank (fderiv ℂ F x) = r) :
    ∃ (phi : LocalBiholomorphAt
          (ComplexEuclidean n) (ComplexEuclidean n) a 0)
      (psi : LocalBiholomorphAt
          (ComplexEuclidean m) (ComplexEuclidean m) (F a) 0),
      (fun x ↦ psi.toFun (F (phi.invFun x))) =ᶠ[nhds 0]
        standardRankMap n m r := by
  obtain ⟨n', hn⟩ := Nat.exists_eq_add_of_le hrn
  obtain ⟨m', hm⟩ := Nat.exists_eq_add_of_le hrm
  subst n
  subst m
  obtain ⟨A, hA⟩ : ∃ A : ComplexEuclidean (r + n') →L[ℂ] ComplexEuclidean (r + m'), fderiv ℂ F a = A := ⟨_, rfl⟩
  let R := LinearMap.range A.toLinearMap
  have hRankR : Module.finrank ℂ R = r := by
    have ha := hconst.self_of_nhds
    rw [hA] at ha
    exact ha
  obtain ⟨Q, hRQ⟩ := Submodule.exists_isCompl R
  have hRQtop : Submodule.IsTopCompl R Q :=
    Submodule.IsCompl.isTopCompl_of_isClosed_of_finiteDimensional hRQ R.closed_of_finiteDimensional
  let : CompleteSpace R := FiniteDimensional.complete ℂ R
  let : CompleteSpace Q := FiniteDimensional.complete ℂ Q
  let pR := R.projectionOntoL Q hRQtop
  let pQ := Q.projectionOntoL R hRQtop.symm
  obtain ⟨targetDecomp, targetDecomp_apply⟩ : ∃ e : ComplexEuclidean (r + m') ≃L[ℂ] R × Q, ∀ y, e y = (pR y, pQ y) :=
    ⟨(Submodule.prodEquivOfIsTopCompl R Q hRQtop).symm, fun y ↦ Submodule.prodEquivOfIsTopCompl_symm_apply hRQtop y⟩
  let g := fun x ↦ pR (F x - F a)
  let g' := pR.comp A
  have hg : AnalyticAt ℂ g a := (pR.analyticAt _).comp (hF.sub analyticAt_const)
  have hgDeriv : HasFDerivAt g g' a := by
    have h := hF.hasStrictFDerivAt.hasFDerivAt
    rw [hA] at h
    exact pR.hasFDerivAt.comp a (h.sub_const (F a))
  have hgSurj : Function.Surjective g' := rangeProjection_comp_surjective A Q hRQtop
  let K := LinearMap.ker g'.toLinearMap
  let : CompleteSpace K := FiniteDimensional.complete ℂ K
  obtain ⟨L, hKL⟩ := Submodule.exists_isCompl K
  have hKLtop : Submodule.IsTopCompl K L :=
    Submodule.IsCompl.isTopCompl_of_isClosed_of_finiteDimensional hKL K.closed_of_finiteDimensional
  let kproj := K.projectionOntoL L hKLtop
  have hkerCompl : IsCompl (LinearMap.ker g'.toLinearMap) (LinearMap.ker kproj.toLinearMap) := by
    change IsCompl K kproj.ker
    rw [Submodule.ker_projectionOntoL hKLtop]
    exact hKL
  let eLin := LinearMap.equivProdOfSurjectiveOfIsCompl g'.toLinearMap kproj.toLinearMap
    (LinearMap.range_eq_top.mpr hgSurj) (Submodule.range_projectionOntoL hKLtop) hkerCompl
  let eDeriv := eLin.toContinuousLinearEquiv
  let H := fun x ↦ (g x, kproj x - kproj a)
  have hHcenter : H a = (0, 0) := by
    change (pR (F a - F a), kproj a - kproj a) = (0, 0)
    rw [sub_self, sub_self, map_zero]
  obtain ⟨chi, hchi⟩ : ∃ chi : LocalBiholomorphAt (ComplexEuclidean (r + n')) (R × K) a (0, 0), chi.toFun = H := by
    rw [← hHcenter]
    exact ⟨LocalBiholomorphAt.ofAnalyticAtOfFDerivEquiv
      (hg.prod ((kproj.analyticAt a).sub analyticAt_const)) eDeriv
      (hgDeriv.prodMk (kproj.hasFDerivAt.sub_const (kproj a))).fderiv, rfl⟩
  have hKrank : Module.finrank ℂ K = n' := by
    have hdim := LinearMap.finrank_range_add_finrank_ker g'.toLinearMap
    rw [LinearMap.range_eq_top.mpr hgSurj, finrank_top, hRankR, Module.finrank_fin_fun] at hdim
    exact Nat.add_left_cancel hdim
  have hQrank : Module.finrank ℂ Q = m' := by
    have hdim := Submodule.finrank_add_eq_of_isCompl hRQ
    rw [hRankR, Module.finrank_fin_fun] at hdim
    exact Nat.add_left_cancel hdim
  let P : R × K → R × Q := fun z ↦ targetDecomp (F (chi.invFun z) - F a)
  have hPAnalytic : AnalyticAt ℂ P 0 := (targetDecomp.toContinuousLinearMap.analyticAt _).comp
    ((hF.comp_of_eq chi.analyticAt_invFun chi.map_target).sub analyticAt_const)
  have hPfst : (fun z ↦ (P z).1) =ᶠ[nhds 0] fun z ↦ z.1 := by
    filter_upwards [chi.right_inv] with z hz
    rw [hchi] at hz
    have hz' := congrArg Prod.fst hz
    change g (chi.invFun z) = z.1 at hz'
    change (targetDecomp _).1 = z.1
    rw [targetDecomp_apply]
    exact hz'
  have hPslice := eventually_snd_eq_slice_of_rank hPAnalytic hPfst (by
    rw [hRankR]
    exact eventually_complexLinearRank_affineConjugate hF chi targetDecomp hconst P rfl)
  let q₀ : R → Q := fun u ↦ (P (u, 0)).2
  have hPzero : P (0, 0) = (0, 0) := by
    change targetDecomp (F (chi.invFun (0, 0)) - F a) = (0, 0)
    rw [chi.map_target, sub_self, map_zero]
    rfl
  obtain ⟨shear, hshear⟩ : ∃ shear : LocalBiholomorphAt (R × Q) (R × Q) 0 0,
      shear.toFun = fun p ↦ (p.1, p.2 - q₀ p.1) :=
    ⟨LocalBiholomorphAt.fiberShearAtZero q₀
      (analyticAt_snd.comp (hPAnalytic.comp_of_eq (analyticAt_id.prod analyticAt_const) (by simp)))
      (congrArg Prod.snd hPzero), rfl⟩
  have hNormal : (fun z ↦ shear.toFun (P z)) =ᶠ[nhds 0] fun z : R × K ↦ (z.1, (0 : Q)) := by
    filter_upwards [hPfst, hPslice] with z hfirst hsecond
    rw [hshear]
    apply Prod.ext hfirst
    change (P z).2 - q₀ (P z).1 = 0
    rw [hfirst, hsecond]
    exact sub_self _
  have eR : R ≃L[ℂ] ComplexEuclidean r := ContinuousLinearEquiv.ofFinrankEq <| by simpa only [Module.finrank_fin_fun] using hRankR
  have eK : K ≃L[ℂ] ComplexEuclidean n' := ContinuousLinearEquiv.ofFinrankEq <| by simpa only [Module.finrank_fin_fun] using hKrank
  have eQ : Q ≃L[ℂ] ComplexEuclidean m' := ContinuousLinearEquiv.ofFinrankEq <| by simpa only [Module.finrank_fin_fun] using hQrank
  let eSource := (eR.prodCongr eK).trans (finProdContinuousLinearEquiv r n')
  let eTarget := (eR.prodCongr eQ).trans (finProdContinuousLinearEquiv r m')
  let sourceCoord := LocalBiholomorphAt.ofContinuousLinearEquivAtZero eSource
  let targetCoord := LocalBiholomorphAt.ofContinuousLinearEquivAtZero eTarget
  let centeredTarget := LocalBiholomorphAt.affine targetDecomp (F a) 0
  refine ⟨chi.trans sourceCoord, centeredTarget.trans (shear.trans targetCoord), ?_⟩
  filter_upwards [sourceCoord.invFun_tendsto hNormal] with x hx
  change shear.toFun (P (eSource.symm x)) = ((eSource.symm x).1, (0 : Q)) at hx
  change eTarget (shear.toFun (targetDecomp (F (chi.invFun (eSource.symm x)) - F a) + 0)) = _
  simpa only [add_zero] using (congrArg eTarget hx).trans
    (productEquiv_fst_zero_eq_standardRankMap r n' m' eR eK eQ x)
