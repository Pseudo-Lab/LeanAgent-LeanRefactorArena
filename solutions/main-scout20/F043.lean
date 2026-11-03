theorem transportedIntegral_continuousOn
    (gradW : PhysSpace d → PhysSpace d)
    (f : ℝ → Measure (PhaseSpace d)) (T : ℝ)
    (hf_mom : ∀ t ∈ Set.Icc (0 : ℝ) T, HasFiniteFirstMoment (f t))
    (hf_narrow : ∀ (g : PhaseSpace d → ℝ), Continuous g → HasCompactSupport g →
      ContinuousOn (fun s => ∫ z, g z ∂(f s)) (Set.Icc 0 T))
    (charX charV : ℝ → PhaseSpace d → PhysSpace d)
    (hflow : IsCharacteristicFlowOn gradW (fun t => spatialMarginal (f t)) charX charV
      (Set.Ioo 0 T) Set.univ)
    (t : ℝ) (ht : t ∈ Set.Ioo (0 : ℝ) T)
    (φ : PhaseSpace d → ℝ) (hφ : ContDiff ℝ (⊤ : ℕ∞) φ) (hφc : HasCompactSupport φ)
    (Ψ : ℝ → PhaseSpace d → PhaseSpace d)
    (hΨ_left : ∀ s ∈ Set.Ioo (0 : ℝ) T,
      Function.LeftInverse (Ψ s) (fun z => (charX s z, charV s z)))
    (hΨ_right : ∀ s ∈ Set.Ioo (0 : ℝ) T,
      Function.RightInverse (Ψ s) (fun z => (charX s z, charV s z)))
    (hΨ_C1 : ContDiffOn ℝ 1 (fun p : ℝ × PhaseSpace d => Ψ p.1 p.2)
      (Set.Ioo 0 T ×ˢ Set.univ))
    (hΦt_C1 : ContDiff ℝ 1 (fun z : PhaseSpace d => (charX t z, charV t z)))
    (L : NNReal)
    (hflowjoint : ContinuousOn (fun p : ℝ × PhaseSpace d => (charX p.1 p.2, charV p.1 p.2))
      (Set.Icc 0 T ×ˢ (Set.univ : Set (PhaseSpace d))))
    (hanti : ∀ s ∈ Set.Ioo (0 : ℝ) T, ∀ z₁ z₂ : PhaseSpace d,
      dist z₁ z₂ ≤ dist ((charX s z₁, charV s z₁) : PhaseSpace d) (charX s z₂, charV s z₂)
        * Real.exp (((max 1 L : NNReal) : ℝ) * s)) :
    ContinuousOn (fun s => if s = 0 then ∫ z, φ (charX t z, charV t z) ∂(f 0)
        else ∫ z, φ (charX t (Ψ s z), charV t (Ψ s z)) ∂(f s)) (Set.Icc (0 : ℝ) t) := by
  classical
  let S : Set (ℝ × PhaseSpace d) := Set.Icc 0 t ×ˢ Set.univ
  let H : ℝ × PhaseSpace d → PhaseSpace d := fun p => if p.1 = 0 then p.2 else Ψ p.1 p.2
  have hinit : ∀ z, (charX 0 z, charV 0 z) = z := fun z =>
    Prod.ext (hflow.1 z (Set.mem_univ z)).1 (hflow.1 z (Set.mem_univ z)).2
  have hright : ∀ p ∈ S, (charX p.1 (H p), charV p.1 (H p)) = p.2 := by
    intro p hp
    by_cases h : p.1 = 0
    · simp only [H, h, if_pos, hinit]
    · simpa only [H, if_neg h] using
        hΨ_right p.1 ⟨lt_of_le_of_ne hp.1.1 (Ne.symm h), lt_of_le_of_lt hp.1.2 ht.2⟩ p.2
  have he : Continuous (fun q : ℝ × PhaseSpace d => Real.exp (((max 1 L : NNReal) : ℝ) * q.1)) :=
    Real.continuous_exp.comp (continuous_const.mul continuous_fst)
  have hH : ContinuousOn H S := by
    intro p hp
    have hc : ContinuousWithinAt (fun q : ℝ × PhaseSpace d => (charX q.1 (H p), charV q.1 (H p))) S p :=
      (hflowjoint.comp (continuous_fst.prodMk continuous_const).continuousOn
        (fun q hq => ⟨⟨hq.1.1, le_trans hq.1.2 ht.2.le⟩, Set.mem_univ _⟩)) p hp
    have hu := (continuous_snd.continuousWithinAt.dist hc).mul he.continuousWithinAt
    rw [ContinuousWithinAt, tendsto_iff_dist_tendsto_zero]
    refine squeeze_zero' (Filter.Eventually.of_forall fun q => dist_nonneg) ?_ (by
      simpa only [hright p hp, dist_self, zero_mul] using hu)
    filter_upwards [self_mem_nhdsWithin] with q hq
    by_cases hq0 : q.1 = 0
    · simp only [H, hq0, if_pos, hinit, mul_zero, Real.exp_zero, mul_one, le_refl]
    · have hh := hanti q.1 ⟨lt_of_le_of_ne hq.1.1 (Ne.symm hq0), lt_of_le_of_lt hq.1.2 ht.2⟩ (H q) (H p)
      rwa [hright q hq] at hh
  let c : ℝ → ℝ := fun r => ↑(Set.projIcc 0 t ht.1.le r)
  have hc : Continuous c := continuous_subtype_val.comp continuous_projIcc
  have hcm : ∀ r, c r ∈ Set.Icc (0 : ℝ) t := fun r => (Set.projIcc 0 t ht.1.le r).2
  have hcid : ∀ r ∈ Set.Icc (0 : ℝ) t, c r = r := fun r hr =>
    congrArg Subtype.val (Set.projIcc_of_mem ht.1.le hr)
  let G : ℝ → PhaseSpace d → ℝ := fun r z => φ (charX t (H (c r,z)), charV t (H (c r,z)))
  have hGc : Continuous (fun p : ℝ × PhaseSpace d => G p.1 p.2) :=
    hφ.continuous.comp (hΦt_C1.continuous.comp
      (hH.comp_continuous (hc.comp continuous_fst |>.prodMk continuous_snd)
        (fun p => ⟨hcm p.1, Set.mem_univ _⟩)))
  have hΨtc : Continuous (Ψ t) := hΨ_C1.continuousOn.comp_continuous
    (continuous_const.prodMk continuous_id) (fun z => ⟨ht, Set.mem_univ _⟩)
  let C := Ψ t '' tsupport φ
  have hC : IsCompact C := hφc.image hΨtc
  let K := (fun p : ℝ × PhaseSpace d => (charX p.1 p.2, charV p.1 p.2)) '' (Set.Icc 0 t ×ˢ C)
  have hK : IsCompact K := (isCompact_Icc.prod hC).image_of_continuousOn
    (hflowjoint.mono fun p hp => ⟨⟨hp.1.1, le_trans hp.1.2 ht.2.le⟩, Set.mem_univ _⟩)
  have hsupp : ∀ r, ∀ z ∉ K, G r z = 0 := by
    intro r z hz
    by_contra hn
    have hm : (charX t (H (c r,z)), charV t (H (c r,z))) ∈ tsupport φ :=
      subset_tsupport _ hn
    have hmem : H (c r,z) ∈ C :=
      ⟨_, hm, hΨ_left t ht (H (c r,z))⟩
    exact hz ⟨(c r,H (c r,z)), ⟨hcm r,hmem⟩, hright (c r,z) ⟨hcm r, Set.mem_univ _⟩⟩
  have hcont := vlasovSolutionOn_integral_continuousOn f T hf_mom hf_narrow G hGc K hK hsupp
  apply (hcont.mono (Set.Icc_subset_Icc_right ht.2.le)).congr
  intro r hr
  simp only [G, hcid r hr, H, Prod.fst, Prod.snd]
  split_ifs with h
  · subst r
    rfl
  · rfl
