theorem exists_chartMatchingControlOn_of_metricSpace
    {S' : Type*} [MetricSpace S']
    (T : PartialTriangulation S') (c : MoiseChart S')
    (U : Set T.toIntrinsic.realization) (hU : IsOpen U)
    (hsub : U ⊆ T.chartOverlap c) :
    ∃ mu : U → ℝ,
      StronglyPositiveOn Set.univ mu ∧
      ∀ (g' : U → c.kind.modelRegion)
        (g : T.toIntrinsic.realization → S'),
        (∀ y : U, g y.1 = (c.chart.symm (g' y)).1) →
        (∀ y : U,
          dist (g' y : Plane)
            (T.chartOverlapMap c ⟨y.1, hsub y.2⟩) ≤ mu y) →
        MatchesAtFrontier U g T.embed ∧
          Disjoint (g '' U) (T.embed '' Uᶜ) := by
  classical
  let model : U → c.kind.modelRegion := fun y ↦
    T.chartOverlapModelMap c ⟨y.1, hsub y.2⟩
  by_cases hComp : Uᶜ.Nonempty
  swap
  · refine ⟨fun _ ↦ 1, fun C _ _ ↦ ⟨1, one_pos, fun _ _ ↦ le_rfl⟩, ?_⟩
    intro g' g _ _
    exact matchesAtFrontier_and_disjoint_of_compl_not_nonempty T U hU hComp g
  let s : U → ℝ := fun y ↦ Metric.infDist (T.embed y.1) (T.embed '' Uᶜ)
  have hs (y : U) : 0 < s y := by
    apply ((hU.isClosed_compl.isCompact.image T.isEmbedding.continuous).isClosed.notMem_iff_infDist_pos (hComp.image _)).mp
    rintro ⟨x, hx, heq⟩
    exact hx (T.isEmbedding.injective heq ▸ y.2)
  let psi : c.kind.modelRegion → S' := fun z ↦ (c.chart.symm z).1
  have hmodelEq (y : U) : psi (model y) = T.embed y.1 :=
    congrArg Subtype.val (c.chart.symm_apply_apply _)
  let A : U → Set ℝ := fun y ↦ {r | r ≤ 1 ∧
    ∀ z : c.kind.modelRegion, dist (z : Plane) (model y : Plane) < r →
      dist (psi z) (T.embed y.1) < s y}
  have hAbdd (y) : BddAbove (A y) := ⟨1, fun r hr ↦ hr.1⟩
  have hUniform : ∀ C : Set U, IsCompact C →
      ∃ δ : ℝ, 0 < δ ∧ ∀ y ∈ C, δ ∈ A y := by
    intro C hC
    rcases C.eq_empty_or_nonempty with rfl | hCne
    · exact ⟨1, one_pos, fun x hx ↦ hx.elim⟩
    obtain ⟨y₀, hy₀, hmin⟩ := hC.exists_isMinOn hCne
      (((Metric.continuous_infDist_pt _).comp
        (T.isEmbedding.continuous.comp continuous_subtype_val)).continuousOn)
    have hu := (hC.image (f := model) ((T.isEmbedding_chartOverlapModelMap c).continuous.comp
      (Continuous.subtype_mk continuous_subtype_val _))).uniformContinuousAt_of_continuousAt psi
      (fun _ _ ↦ (continuous_subtype_val.comp c.chart.symm.continuous).continuousAt)
      (Metric.dist_mem_uniformity (hs y₀))
    obtain ⟨δ, hδ, hclose⟩ := Metric.mem_uniformity_dist.mp hu
    refine ⟨min δ 1, lt_min hδ one_pos, fun y hy ↦ ⟨min_le_right _ _, ?_⟩⟩
    intro z hz
    apply lt_of_lt_of_le _ (hmin hy)
    rw [← hmodelEq y, dist_comm]
    exact hclose (by
      rw [dist_comm, Subtype.dist_eq]
      exact hz.trans_le (min_le_left _ _)) ⟨y, hy, rfl⟩
  refine ⟨fun y ↦ sSup (A y) / 2, ?_, ?_⟩
  · intro C hC _
    obtain ⟨δ, hδ, hm⟩ := hUniform C hC
    exact ⟨δ / 2, half_pos hδ, fun y hy ↦
      div_le_div_of_nonneg_right (le_csSup (hAbdd y) (hm y hy)) zero_le_two⟩
  · intro g' g hg hclose
    have close (y : U) : dist (g y.1) (T.embed y.1) < s y := by
      obtain ⟨δ, hδ, hm⟩ := hUniform {y} isCompact_singleton
      obtain ⟨r, hr, hlt⟩ := exists_lt_of_lt_csSup ⟨δ, hm y rfl⟩
        (half_lt_self (hδ.trans_le (le_csSup (hAbdd y) (hm y rfl))))
      rw [hg y]
      exact hr.2 (g' y) ((hclose y).trans_lt hlt)
    constructor
    · intro x hx
      have hb := (T.isEmbedding.continuous.tendsto x).mono_left (nhdsWithin_le_nhds (s := U))
      apply hb.congr_dist
      apply squeeze_zero' (Filter.Eventually.of_forall fun _ ↦ dist_nonneg) ?_
        (tendsto_iff_dist_tendsto_zero.mp hb)
      filter_upwards [self_mem_nhdsWithin] with y hy
      rw [dist_comm]
      exact (close ⟨y, hy⟩).le.trans (Metric.infDist_le_dist_of_mem
        ⟨x, by simpa only [Set.mem_compl_iff, hU.interior_eq] using hx.2, rfl⟩)
    · rw [Set.disjoint_left]
      rintro z ⟨x, hx, rfl⟩ ⟨y, hy, heq⟩
      have hi := (close ⟨x, hx⟩).trans_le
        (Metric.infDist_le_dist_of_mem ⟨y, hy, rfl⟩)
      rw [heq, dist_comm] at hi
      exact lt_irrefl _ hi
