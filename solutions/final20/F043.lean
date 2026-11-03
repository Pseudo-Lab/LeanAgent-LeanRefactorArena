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
  let F : ℝ → PhaseSpace d → PhaseSpace d := fun s z => (charX s z, charV s z)
  let c : ℝ := ((max 1 L : NNReal) : ℝ)
  have hinit : ∀ z, F 0 z = z := fun z =>
    Prod.ext (hflow.1 z (Set.mem_univ z)).1 (hflow.1 z (Set.mem_univ z)).2
  let u : ℝ → ℝ := fun s => max 0 (min s t)
  have hu : Continuous u := continuous_const.max (continuous_id.min continuous_const)
  have hub : ∀ s, u s ∈ Set.Icc 0 t := fun s =>
    ⟨le_max_left _ _, max_le ht.1.le (min_le_right _ _)⟩
  have huneg : ∀ s, s ≤ 0 → u s = 0 := fun s hs =>
    max_eq_left ((min_le_left _ _).trans hs)
  have hupos : ∀ s, 0 < s → u s ∈ Set.Ioo (0 : ℝ) T := fun s hs =>
    ⟨lt_max_of_lt_right (lt_min hs ht.1), (hub s).2.trans_lt ht.2⟩
  let H : ℝ → PhaseSpace d → PhaseSpace d :=
    fun s z => if s ≤ 0 then z else Ψ (u s) z
  have hright : ∀ s z, F (u s) (H s z) = z := by
    intro s z
    dsimp only [H]
    split_ifs with hs
    · rw [huneg s hs, hinit]
    · exact hΨ_right _ (hupos s (lt_of_not_ge hs)) z
  have hbound : ∀ s x y, dist x y ≤
      dist (F (u s) x) (F (u s) y) * Real.exp (c * u s) := by
    intro s x y
    by_cases hs : s ≤ 0
    · simp only [huneg s hs, hinit, mul_zero, Real.exp_zero, mul_one, le_refl]
    · exact hanti (u s) (hupos s (lt_of_not_ge hs)) x y
  have hH : Continuous (fun p : ℝ × PhaseSpace d => H p.1 p.2) := by
    rw [continuous_iff_continuousAt]
    intro p
    rw [ContinuousAt, tendsto_iff_dist_tendsto_zero]
    have hc : Continuous (fun q : ℝ × PhaseSpace d =>
        dist q.2 (F (u q.1) (H p.1 p.2)) * Real.exp (c * u q.1)) :=
      (continuous_snd.dist (hflowjoint.comp_continuous
        ((hu.comp continuous_fst).prodMk continuous_const)
        (fun q => ⟨⟨(hub q.1).1, (hub q.1).2.trans ht.2.le⟩, Set.mem_univ _⟩))).mul
        (Real.continuous_exp.comp (continuous_const.mul (hu.comp continuous_fst)))
    exact squeeze_zero (fun q => dist_nonneg)
      (fun q => by simpa only [hright] using hbound q.1 (H q.1 q.2) (H p.1 p.2))
      (by simpa only [hright, dist_self, zero_mul] using hc.tendsto p)
  let S := H t '' tsupport φ
  let G : ℝ → PhaseSpace d → ℝ := fun s z => φ (F t (H s z))
  let K := (fun q : ℝ × PhaseSpace d => F q.1 q.2) '' (Set.Icc 0 t ×ˢ S)
  have hK : IsCompact K :=
    (isCompact_Icc.prod (hφc.image (hH.comp (continuous_const.prodMk continuous_id)))).image_of_continuousOn
      (hflowjoint.mono (Set.prod_mono (Set.Icc_subset_Icc_right ht.2.le) (Set.subset_univ S)))
  have hsupp : ∀ s, ∀ z ∉ K, G s z = 0 := by
    intro s z hz
    by_contra hn
    apply hz
    refine ⟨(u s, H s z), ⟨hub s, ⟨F t (H s z), subset_tsupport φ hn, ?_⟩⟩, hright s z⟩
    simpa only [H, if_neg (not_le.mpr ht.1), u, min_self, max_eq_right ht.1.le] using hΨ_left t ht (H s z)
  refine ((vlasovSolutionOn_integral_continuousOn f T hf_mom hf_narrow G
    ((hφ.continuous.comp hΦt_C1.continuous).comp hH) K hK hsupp).mono
      (Set.Icc_subset_Icc_right ht.2.le)).congr ?_
  intro s hs
  rcases eq_or_lt_of_le hs.1 with he | he
  · subst s
    simp only [G, H, F, le_refl, ite_true]
  · have hus : u s = s := by
      dsimp only [u]
      rw [min_eq_left hs.2, max_eq_right hs.1]
    simp only [G, H, F, if_neg (not_le.mpr he), if_neg (ne_of_gt he), hus]
