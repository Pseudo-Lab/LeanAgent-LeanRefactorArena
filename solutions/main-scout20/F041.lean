theorem erlv_case12_other_d1_bone_impossible
    {n : ℕ} [NeZero n] {P : Fin n → Point ℝ} {d₁ d₂ d₃ : ℝ}
    (S : ErLVAtVertexUseSite P d₁ d₂ d₃) (h12 : S.Case12)
    (hOther : sqDist
      (P (cyclicRetreat (firstClockwiseNeighbor P d₁ d₂ d₃ S.x)
        S.pair.first.leftMoves))
      (P (cyclicAdvance S.x 1)) = d₁)
    (hBOne : S.pair.first.leftMoves = 1) : False := by
  let x := S.x
  let p := cyclicAdvance x 1
  let q := cyclicAdvance x 2
  let u := firstCounterclockwiseNeighbor P d₁ d₂ d₃ (cyclicAdvance x 3)
  let z := firstClockwiseNeighbor P d₁ d₂ d₃ x
  let s := cyclicRetreat z 1
  let uoff := erlvUOffset S
  let zoff := erlvZOffset S
  let soff := zoff - 1
  have hOffsets := erlv_u_z_offset_data S
  have huoff3 : 3 < uoff := hOffsets.1
  have huz : uoff + 3 ≤ zoff := hOffsets.2.1
  have hzoffn : zoff < n := hOffsets.2.2.1
  have hsoffn : soff < n := by dsimp [soff]; omega
  have huS : uoff < soff := by dsimp [soff]; omega
  have hsZ : soff < zoff := by dsimp [soff]; omega
  have huIndex : u = cyclicAdvance x uoff := hOffsets.2.2.2.1
  have hzIndex : z = cyclicAdvance x zoff := hOffsets.2.2.2.2
  have hsIndex : s = cyclicAdvance x soff := by
    dsimp [s]
    rw [hzIndex]
    exact cyclicRetreat_advance x (k := zoff) (m := 1) (by omega) hzoffn
  have hData := erlv_case12_shared_tip_rank_data S h12
  have hpu : sqDist (P p) (P u) = d₁ := hData.1
  have hqu : sqDist (P q) (P u) = d₂ := hData.2.2
  have hsp : sqDist (P s) (P p) = d₁ := by
    rw [hBOne] at hOther
    exact hOther
  have hps : sqDist (P p) (P s) = d₁ := by
    simpa only [sqDist_comm] using hsp
  have hpzNe : sqDist (P p) (P z) ≠ d₁ := by
    intro hpz
    have hquad₁ : StrictConvexQuad (P p) (P q) (P u) (P s) := by
      have h := cyclic_strict_convex_quad_offsets S.convex x
        (a := 1) (b := 2) (c := uoff) (d := soff)
        (by omega) (by omega) huS hsoffn
      rw [← huIndex, ← hsIndex] at h
      exact h
    have hquad₂ : StrictConvexQuad (P p) (P q) (P s) (P z) := by
      have h := cyclic_strict_convex_quad_offsets S.convex x
        (a := 1) (b := 2) (c := soff) (d := zoff)
        (by omega) (by omega) hsZ hzoffn
      rw [← hsIndex, ← hzIndex] at h
      exact h
    have hgrow₁ := equal_radius_arc_strict_order hquad₁ (hpu.trans hps.symm)
    have hgrow₂ := equal_radius_arc_strict_order hquad₂ (hps.trans hpz.symm)
    have hqsNe : q ≠ s := by
      rw [hsIndex]
      exact cyclicAdvance_ne_of_lt x (by omega) hsoffn (by omega)
    have hqzNe : q ≠ z := by
      rw [hzIndex]
      exact cyclicAdvance_ne_of_lt x (by omega) hzoffn (by omega)
    have hbz := (top_three_class_bounds_of_ne S.classes hqzNe).1
    have hbs := (top_three_class_bounds_of_ne S.classes hqsNe).2.1
      (lt_of_lt_of_le hgrow₂ hbz)
    linarith only [hgrow₁, hqu, hbs]
  have hFirstPath : K3CoverSequence P z x 1 1 := by
    simpa only [z, x, hBOne, h12.1] using S.pair.first.path
  have hStart : TopThreeAdjacent P d₁ d₂ d₃ z x := S.first_start_adjacent
  have hRanks : sqDist (P x) (P z) = d₃ ∧ sqDist (P p) (P z) = d₂ := by
    cases hFirstPath with
    | left hLeft tailPath =>
      cases tailPath with
      | right hRight _ =>
        have hMid := left_cover_top_three_adjacent S.classes hStart hLeft
        have hr := strict_three_rank_chain S.classes.1 S.classes.2.1
          hStart.2 hMid.2 (Or.inl hsp) hLeft hRight
        have hxz : sqDist (P x) (P z) = d₃ := by
          simpa only [sqDist_comm] using hr.1
        have hxs : sqDist (P x) (P s) = d₂ := by
          simpa only [sqDist_comm] using hr.2.1
        have hquad : StrictConvexQuad (P x) (P p) (P s) (P z) := by
          have h := cyclic_strict_convex_quad_offsets S.convex x
            (a := 0) (b := 1) (c := soff) (d := zoff)
            (by omega) (by omega) hsZ hzoffn
          rw [← hsIndex, ← hzIndex] at h
          simpa [p] using h
        have hcompare := far_arc_strict_center_comparison hquad
          (show sqDist (P x) (P s) ≤ sqDist (P p) (P s) by
            rw [hxs, hps]
            exact le_of_lt S.classes.2.1)
        have hpzAdj := top_three_adjacent_of_strictly_longer S.classes
          (topThreeAdjacent_symm hStart) hcompare
        refine ⟨hxz, ?_⟩
        rcases hpzAdj.2 with h | h | h
        · exact (hpzNe h).elim
        · exact h
        · linarith only [hxz, h, hcompare]
    | right hRight tailPath =>
      cases tailPath with
      | left hLeft _ =>
        have hMid := right_cover_top_three_adjacent S.classes hStart hRight
        have hr := strict_three_rank_chain S.classes.1 S.classes.2.1
          hStart.2 hMid.2 (Or.inl hsp) hRight hLeft
        constructor
        · simpa only [sqDist_comm] using hr.1
        · simpa only [sqDist_comm] using hr.2.1
  have hxu := d1_d3_opposite_sides_force_xu_top_two S.classes
    (erlv_x_p_u_z_strict_convex_quad S)
    (topThreeAdjacent_symm S.first_start_adjacent) hpu hRanks.1 hRanks.2
  have hbounds := maximal_gap_tail_degree_bounds S hpu hRanks.1 hRanks.2
  rcases hxu with h | h
  · exact high_degree_le_six_false S S.x (hbounds.1 h)
  · exact high_degree_le_six_false S S.x ((hbounds.2 h).trans (by omega))
