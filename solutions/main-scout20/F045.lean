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
  let A := fderiv ℂ F a
  let R := LinearMap.range A.toLinearMap
  have hRankR : Module.finrank ℂ R = r := hconst.self_of_nhds
  obtain ⟨Q, hRQ⟩ := Submodule.exists_isCompl R
  have hRQtop : Submodule.IsTopCompl R Q :=
    Submodule.IsCompl.isTopCompl_of_isClosed_of_finiteDimensional hRQ
      R.closed_of_finiteDimensional
  let : CompleteSpace R := FiniteDimensional.complete ℂ R
  let : CompleteSpace Q := FiniteDimensional.complete ℂ Q
  let pR := R.projectionOntoL Q hRQtop
  let pQ := Q.projectionOntoL R hRQtop.symm
  let targetDecomp := (Submodule.prodEquivOfIsTopCompl R Q hRQtop).symm
  have targetDecomp_apply (y : ComplexEuclidean (r + m')) :
      targetDecomp y = (pR y, pQ y) := by
    simp [targetDecomp, pR, pQ]
  let g := fun x ↦ pR (F x - F a)
  let g' := pR.comp A
  have hg : AnalyticAt ℂ g a :=
    (pR.analyticAt _).comp (hF.sub analyticAt_const)
  have hgDeriv : HasFDerivAt g g' a :=
    pR.hasFDerivAt.comp a (hF.hasStrictFDerivAt.hasFDerivAt.sub_const (F a))
  have hgSurj : Function.Surjective g' :=
    rangeProjection_comp_surjective A Q hRQtop
  let K := LinearMap.ker g'.toLinearMap
  let : CompleteSpace K := FiniteDimensional.complete ℂ K
  obtain ⟨L, hKL⟩ := Submodule.exists_isCompl K
  have hKLtop : Submodule.IsTopCompl K L :=
    Submodule.IsCompl.isTopCompl_of_isClosed_of_finiteDimensional hKL
      K.closed_of_finiteDimensional
  let kproj := K.projectionOntoL L hKLtop
  have hkerCompl : IsCompl (LinearMap.ker g'.toLinearMap)
      (LinearMap.ker kproj.toLinearMap) := by
    simpa [K, kproj] using hKL
  let eLin := LinearMap.equivProdOfSurjectiveOfIsCompl g'.toLinearMap kproj.toLinearMap
      (LinearMap.range_eq_top.mpr hgSurj)
      (Submodule.range_projectionOntoL hKLtop) hkerCompl
  let eDeriv := eLin.toContinuousLinearEquiv
  let H := fun x ↦ (g x, kproj (x - a))
  have hHAnalytic : AnalyticAt ℂ H a :=
    hg.prod ((kproj.analyticAt _).comp (analyticAt_id.sub analyticAt_const))
  have hkDeriv : HasFDerivAt (fun x ↦ kproj (x - a)) kproj a := by
    simpa only [map_sub] using kproj.hasFDerivAt.sub_const (kproj a)
  have hHfderiv : fderiv ℂ H a = (eDeriv : _ →L[ℂ] _) :=
    (hgDeriv.prodMk hkDeriv).fderiv
  let chiRaw := LocalBiholomorphAt.ofAnalyticAtOfFDerivEquiv
    hHAnalytic eDeriv hHfderiv
  have hHcenter : H a = (0, 0) := by simp only [H, g, sub_self, map_zero]
  let chi : LocalBiholomorphAt
      (ComplexEuclidean (r + n')) (R × K) a (0, 0) :=
    { toFun := H
      invFun := chiRaw.invFun
      map_source := hHcenter
      map_target := hHcenter ▸ chiRaw.map_target
      analyticAt_toFun := hHAnalytic
      analyticAt_invFun := hHcenter ▸ chiRaw.analyticAt_invFun
      left_inv := chiRaw.left_inv
      right_inv := hHcenter ▸ chiRaw.right_inv }
  have hKrank : Module.finrank ℂ K = n' := by
    have hdim := LinearMap.finrank_range_add_finrank_ker g'.toLinearMap
    rw [LinearMap.range_eq_top.mpr hgSurj, finrank_top,
      hRankR, Module.finrank_fin_fun] at hdim
    exact Nat.add_left_cancel hdim
  have hQrank : Module.finrank ℂ Q = m' := by
    have hdim := Submodule.finrank_add_eq_of_isCompl hRQ
    rw [hRankR, Module.finrank_fin_fun] at hdim
    exact Nat.add_left_cancel hdim
  let P : R × K → R × Q := fun z ↦ targetDecomp (F (chi.invFun z) - F a)
  have hPAnalytic : AnalyticAt ℂ P 0 := by
    have hinner : AnalyticAt ℂ (fun z ↦ F (chi.invFun z) - F a) 0 :=
      (hF.comp_of_eq chi.analyticAt_invFun chi.map_target).sub analyticAt_const
    exact (targetDecomp.toContinuousLinearMap.analyticAt _).comp hinner
  have hPfst : (fun z ↦ (P z).1) =ᶠ[nhds 0] fun z ↦ z.1 := by
    filter_upwards [chi.right_inv] with z hz
    have hz' := congrArg Prod.fst hz
    change g (chi.invFun z) = z.1 at hz'
    simpa only [P, targetDecomp_apply, g] using hz'
  have hPrank : ∀ᶠ z in nhds 0,
      complexLinearRank (fderiv ℂ P z) = Module.finrank ℂ R :=
    (eventually_complexLinearRank_affineConjugate hF chi targetDecomp hconst P rfl).mono
      fun z hz ↦ hz.trans hRankR.symm
  have hPslice := eventually_snd_eq_slice_of_rank hPAnalytic hPfst hPrank
  let q₀ : R → Q := fun u ↦ (P (u, 0)).2
  have hq₀Analytic : AnalyticAt ℂ q₀ 0 := by
    exact analyticAt_snd.comp (hPAnalytic.comp_of_eq
      (analyticAt_id.prod analyticAt_const) (by simp))
  have hPzero : P (0, 0) = (0, 0) := by
    change targetDecomp (F (chi.invFun (0, 0)) - F a) = (0, 0)
    rw [chi.map_target, sub_self, map_zero]
    rfl
  let shear := LocalBiholomorphAt.fiberShearAtZero q₀ hq₀Analytic
    (congrArg Prod.snd hPzero)
  have hNormal : (fun z ↦ shear.toFun (P z)) =ᶠ[nhds 0]
      fun z : R × K ↦ (z.1, (0 : Q)) := by
    filter_upwards [hPfst, hPslice] with z hfirst hsecond
    exact Prod.ext hfirst (sub_eq_zero.mpr
      (hsecond.trans (congrArg q₀ hfirst).symm))
  let eR : R ≃L[ℂ] ComplexEuclidean r :=
    ContinuousLinearEquiv.ofFinrankEq <| by
      simpa only [Module.finrank_fin_fun] using hRankR
  let eK : K ≃L[ℂ] ComplexEuclidean n' :=
    ContinuousLinearEquiv.ofFinrankEq <| by
      simpa only [Module.finrank_fin_fun] using hKrank
  let eQ : Q ≃L[ℂ] ComplexEuclidean m' :=
    ContinuousLinearEquiv.ofFinrankEq <| by
      simpa only [Module.finrank_fin_fun] using hQrank
  let eSource := (eR.prodCongr eK).trans (finProdContinuousLinearEquiv r n')
  let eTarget := (eR.prodCongr eQ).trans (finProdContinuousLinearEquiv r m')
  let sourceCoord := LocalBiholomorphAt.ofContinuousLinearEquivAtZero eSource
  let targetCoord := LocalBiholomorphAt.ofContinuousLinearEquivAtZero eTarget
  let centeredTarget := LocalBiholomorphAt.affine targetDecomp (F a) 0
  let phi := chi.trans sourceCoord
  let psi := centeredTarget.trans (shear.trans targetCoord)
  refine ⟨phi, psi, ?_⟩
  filter_upwards [sourceCoord.invFun_tendsto hNormal] with x hx
  change shear.toFun (P (eSource.symm x)) = ((eSource.symm x).1, (0 : Q)) at hx
  calc
    psi.toFun (F (phi.invFun x)) = eTarget (shear.toFun (P (eSource.symm x))) :=
      congrArg (fun z ↦ eTarget (shear.toFun z)) (add_zero _)
    _ = eTarget ((eSource.symm x).1, (0 : Q)) := congrArg eTarget hx
    _ = standardRankMap (r + n') (r + m') r x :=
      productEquiv_fst_zero_eq_standardRankMap r n' m' eR eK eQ x
