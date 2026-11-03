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
  obtain ⟨huoff3, huz, hzoffn, huIndex, hzIndex⟩ := erlv_u_z_offset_data S
  change u = cyclicAdvance x uoff at huIndex
  change z = cyclicAdvance x zoff at hzIndex
  obtain ⟨hus, hsz⟩ : uoff < soff ∧ soff < zoff := by omega
  have hu2 : 2 < uoff := lt_trans (by decide) huoff3
  have hsn := hsz.trans hzoffn
  have hun := hus.trans hsn
  have h0u := Nat.zero_lt_of_lt huoff3
  have h2s := hu2.trans hus
  have hps : sqDist (P p) (P s) = d₁ := by
    change sqDist (P (cyclicRetreat z S.pair.first.leftMoves)) (P p) = d₁ at hOther
    simpa only [hBOne, hzIndex,
      cyclicRetreat_advance x (Nat.zero_lt_of_lt hsz) hzoffn, sqDist_comm] using hOther
  have hData := erlv_case12_shared_tip_rank_data S h12
  have hpzNe : sqDist (P p) (P z) ≠ d₁ := by
    intro hpz
    have hquad₁ := cyclic_strict_convex_quad_offsets S.convex x
      (a := 1) (b := 2) (c := uoff) (d := soff)
      (by decide) hu2 hus hsn
    rw [← huIndex] at hquad₁
    have hgrow := equal_radius_arc_strict_order hquad₁ (hData.1.trans hps.symm)
    have hquad₂ := cyclic_strict_convex_quad_offsets S.convex x
      (a := 1) (b := 2) (c := soff) (d := zoff)
      (by decide) h2s hsz hzoffn
    rw [← hzIndex] at hquad₂
    have hg := equal_radius_arc_strict_order hquad₂ (hps.trans hpz.symm)
    have hqzNe : q ≠ z := by
      rw [hzIndex]
      exact cyclicAdvance_ne_of_lt x (h2s.trans hsn) hzoffn (h2s.trans hsz).ne
    exact not_lt_of_ge
      ((top_three_class_bounds_of_ne S.classes
        (cyclicAdvance_ne_of_lt x (h2s.trans hsn) hsn h2s.ne)).2.1
        (hg.trans_le (top_three_class_bounds_of_ne S.classes hqzNe).1))
      (hData.2.2.symm.trans_lt hgrow)
  have hxuNe : x ≠ u := by
    rw [huIndex]
    simpa only [cyclicAdvance_zero] using
      (cyclicAdvance_ne_of_lt x (h0u.trans hun) hun h0u.ne)
  have hquad := erlv_x_p_u_z_strict_convex_quad S
  have hcompare := far_arc_strict_center_comparison hquad (by
    rw [hData.1]
    exact (top_three_class_bounds_of_ne S.classes hxuNe).1)
  have hxzAdj := topThreeAdjacent_symm S.first_start_adjacent
  rcases strict_top_three_rank_slots S.classes hxzAdj
      (top_three_adjacent_of_strictly_longer S.classes hxzAdj hcompare) hcompare with h | h | h <;>
    try exact hpzNe h.2
  have hxu := d1_d3_opposite_sides_force_xu_top_two S.classes hquad hxzAdj hData.1 h.1 h.2
  have hb := maximal_gap_tail_degree_bounds S hData.1 h.1 h.2
  apply high_degree_le_six_false S S.x
  exact hxu.elim hb.1 (fun hu => (hb.2 hu).trans (by decide))
