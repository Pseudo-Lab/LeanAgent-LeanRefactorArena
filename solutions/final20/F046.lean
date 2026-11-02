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
  let model : U → c.kind.modelRegion := fun y ↦ T.chartOverlapModelMap c ⟨y.1, hsub y.2⟩
  by_cases hComp : Uᶜ.Nonempty
  swap
  · refine ⟨fun _ ↦ 1, fun C _ _ ↦ ⟨1, one_pos, fun _ _ ↦ le_rfl⟩, ?_⟩
    intro g' g hgval hclose
    exact matchesAtFrontier_and_disjoint_of_compl_not_nonempty T U hU hComp g
  have hCompCompact : IsCompact (T.embed '' Uᶜ) :=
    hU.isClosed_compl.isCompact.image T.isEmbedding.continuous
  let sS : U → ℝ := fun y ↦ Metric.infDist (T.embed y.1) (T.embed '' Uᶜ)
  have hsSpos : ∀ y : U, 0 < sS y := by
    intro y
    apply (hCompCompact.isClosed.notMem_iff_infDist_pos (hComp.image _)).mp
    rintro ⟨x, hxComp, hxy⟩
    exact hxComp (T.isEmbedding.injective hxy ▸ y.2)
  let psi : c.kind.modelRegion → S' := fun z ↦ (c.chart.symm z).1
  have hpsiModel (y : U) : psi (model y) = T.embed y.1 :=
    congrArg Subtype.val (c.chart.symm_apply_apply (T.chartOverlapToDomain c ⟨y.1, hsub y.2⟩))
  let A : U → Set ℝ := fun y ↦
    {r | r ≤ 1 ∧ ∀ z : c.kind.modelRegion,
      dist (z : Plane) (model y : Plane) < r → dist (psi z) (T.embed y.1) < sS y}
  have hAbdd : ∀ y, BddAbove (A y) := fun y ↦ ⟨1, fun r hr ↦ hr.1⟩
  have hUniform : ∀ C : Set U, IsCompact C → C.Nonempty →
      ∃ δ : ℝ, 0 < δ ∧ ∀ y ∈ C, δ ∈ A y := by
    intro C hC hCne
    obtain ⟨y₀, hy₀C, hy₀min⟩ := hC.exists_isMinOn hCne
      (show Continuous sS from (Metric.continuous_infDist_pt _).comp
        (T.isEmbedding.continuous.comp continuous_subtype_val)).continuousOn
    have hu := (hC.image (show Continuous model from
      (T.isEmbedding_chartOverlapModelMap c).continuous.comp
        (Continuous.subtype_mk continuous_subtype_val _))).uniformContinuousAt_of_continuousAt psi
      (fun _ _ ↦ (continuous_subtype_val.comp c.chart.symm.continuous).continuousAt)
      (Metric.dist_mem_uniformity (hsSpos y₀))
    obtain ⟨δ, hδ, hδclose⟩ := Metric.mem_uniformity_dist.mp hu
    refine ⟨min δ 1, lt_min hδ one_pos, fun y hyC ↦ ⟨min_le_right _ _, ?_⟩⟩
    intro z hz
    have hdist : dist (model y) z < δ := by
      rw [dist_comm, Subtype.dist_eq]
      exact hz.trans_le (min_le_left _ _)
    have hlt : dist (psi (model y)) (psi z) < sS y₀ :=
      hδclose hdist (Set.mem_image_of_mem model hyC)
    rw [hpsiModel, dist_comm] at hlt
    exact hlt.trans_le (hy₀min hyC)
  refine ⟨fun y ↦ sSup (A y) / 2, ?_, ?_⟩
  · intro C hC _
    rcases C.eq_empty_or_nonempty with rfl | hCne
    · exact ⟨1, one_pos, fun x hx ↦ absurd hx (Set.notMem_empty x)⟩
    obtain ⟨δ, hδ, hmem⟩ := hUniform C hC hCne
    exact ⟨δ / 2, half_pos hδ,
      fun y hy ↦ div_le_div_of_nonneg_right (le_csSup (hAbdd y) (hmem y hy)) zero_le_two⟩
  · intro g' g hgval hclose
    have replacementClose (y : U) : dist (g y.1) (T.embed y.1) < sS y := by
      obtain ⟨a, hapos, hmem⟩ := hUniform {y} isCompact_singleton ⟨y, rfl⟩
      have ha := hmem y rfl
      obtain ⟨r, hrA, hr⟩ := exists_lt_of_lt_csSup ⟨a, ha⟩
        (half_lt_self (hapos.trans_le (le_csSup (hAbdd y) ha)))
      rw [show g y.1 = psi (g' y) from hgval y]
      exact hrA.2 (g' y) (lt_of_le_of_lt (hclose y) hr)
    constructor
    · intro x hx
      have ht := (T.isEmbedding.continuous.tendsto x).mono_left (nhdsWithin_le_nhds (s := U))
      apply ht.congr_dist
      apply squeeze_zero' (Filter.Eventually.of_forall fun _ ↦ dist_nonneg) ?_
        (tendsto_iff_dist_tendsto_zero.mp ht)
      filter_upwards [self_mem_nhdsWithin] with y hy
      have hxcomp : x ∈ Uᶜ := by
        rw [← frontier_compl U] at hx
        exact hU.isClosed_compl.frontier_subset hx
      rw [dist_comm]
      exact (replacementClose ⟨y, hy⟩).le.trans
        (Metric.infDist_le_dist_of_mem ⟨x, hxcomp, rfl⟩)
    · rw [Set.disjoint_left]
      rintro z ⟨x, hxU, rfl⟩ ⟨y, hyComp, hyEq⟩
      apply Metric.notMem_of_dist_lt_infDist (x := T.embed x) (y := g x)
        (s := T.embed '' Uᶜ) ?_ ⟨y, hyComp, hyEq⟩
      rw [dist_comm]
      exact replacementClose ⟨x, hxU⟩
