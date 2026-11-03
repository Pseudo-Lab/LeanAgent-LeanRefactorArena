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
  let uoff := erlvUOffset S
  let zoff := erlvZOffset S
  let soff := zoff - 1
  let s := cyclicAdvance x soff
  obtain ⟨huoff3, huz, hzoffn, huIndex, hzIndex⟩ :
      3 < uoff ∧ uoff + 3 ≤ zoff ∧ zoff < n ∧
        u = cyclicAdvance x uoff ∧ z = cyclicAdvance x zoff := erlv_u_z_offset_data S
  have hs : 2 < soff ∧ soff < zoff ∧ soff < n ∧ uoff < soff := by omega
  have hu : 0 < uoff ∧ uoff < n := by omega
  have hps : sqDist (P p) (P s) = d₁ := by
    rw [hBOne] at hOther
    change sqDist (P (cyclicRetreat z 1)) (P p) = d₁ at hOther
    rw [hzIndex, cyclicRetreat_advance x (by omega) hzoffn] at hOther
    exact (sqDist_comm _ _).trans hOther
  have hData := erlv_case12_shared_tip_rank_data S h12
  have hpzNe : sqDist (P p) (P z) ≠ d₁ := by
    intro hpz
    have hquad₁ := cyclic_strict_convex_quad_offsets S.convex x
      (a := 1) (b := 2) (c := uoff) (d := soff)
      (by decide) (lt_trans (by decide) huoff3) hs.2.2.2 hs.2.2.1
    rw [← huIndex] at hquad₁
    have hgrow := equal_radius_arc_strict_order hquad₁ (hData.1.trans hps.symm)
    have hqsNe : q ≠ s :=
      cyclicAdvance_ne_of_lt x (hs.1.trans hs.2.2.1) hs.2.2.1 hs.1.ne
    have hquad₂ := cyclic_strict_convex_quad_offsets S.convex x
      (a := 1) (b := 2) (c := soff) (d := zoff)
      (by decide) hs.1 hs.2.1 hzoffn
    rw [← hzIndex] at hquad₂
    have hg := equal_radius_arc_strict_order hquad₂ (hps.trans hpz.symm)
    have hqzNe : q ≠ z := by
      rw [hzIndex]
      exact cyclicAdvance_ne_of_lt x (hs.1.trans hs.2.2.1) hzoffn (hs.1.trans hs.2.1).ne
    exact not_lt_of_ge
      ((top_three_class_bounds_of_ne S.classes hqsNe).2.1
        (hg.trans_le (top_three_class_bounds_of_ne S.classes hqzNe).1))
      (hData.2.2.symm.trans_lt hgrow)
  have hxuNe : x ≠ u := by
    rw [huIndex]
    simpa only [cyclicAdvance_zero] using
      (cyclicAdvance_ne_of_lt x (hu.1.trans hu.2) hu.2 hu.1.ne)
  have hquad := erlv_x_p_u_z_strict_convex_quad S
  have hcompare := far_arc_strict_center_comparison hquad (by
    rw [hData.1]
    exact (top_three_class_bounds_of_ne S.classes hxuNe).1)
  have hxzAdj := topThreeAdjacent_symm S.first_start_adjacent
  rcases strict_top_three_rank_slots S.classes hxzAdj
      (top_three_adjacent_of_strictly_longer S.classes hxzAdj hcompare) hcompare with h | h | h
  · exact hpzNe h.2
  · exact hpzNe h.2
  · have hxu := d1_d3_opposite_sides_force_xu_top_two S.classes hquad hxzAdj hData.1 h.1 h.2
    have hb := maximal_gap_tail_degree_bounds S hData.1 h.1 h.2
    apply high_degree_le_six_false S S.x
    exact hxu.elim hb.1 (fun hu => (hb.2 hu).trans (by decide))
