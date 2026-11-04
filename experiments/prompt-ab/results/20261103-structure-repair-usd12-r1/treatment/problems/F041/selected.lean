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
  let uoff := erlvUOffset S
  let zoff := erlvZOffset S
  let soff := zoff - 1
  obtain ⟨huoff3, huz, hzoffn, huIndex, hzIndex⟩ := erlv_u_z_offset_data S
  have hs : 2 < soff ∧ soff < zoff ∧ soff < n ∧ uoff < soff := by omega
  have hb {a b : ℕ} (hab : a < b) (hbn : b < n) :=
    top_three_class_bounds_of_ne S.classes
      (cyclicAdvance_ne_of_lt x (hab.trans hbn) hbn hab.ne)
  have hps : sqDist (P p) (P (cyclicAdvance x soff)) = d₁ := by
    rw [sqDist_comm, ← cyclicRetreat_advance x (m := 1) (by omega) hzoffn, ← hzIndex]
    exact hBOne ▸ hOther
  have hData := erlv_case12_shared_tip_rank_data S h12
  have hpzNe : sqDist (P p) (P (firstClockwiseNeighbor P d₁ d₂ d₃ x)) ≠ d₁ := by
    intro hpz
    have hquad₁ := cyclic_strict_convex_quad_offsets S.convex x
      (a := 1) (b := 2) (c := uoff) (d := soff)
      (by decide) (lt_trans (by decide) huoff3) hs.2.2.2 hs.2.2.1
    rw [← huIndex] at hquad₁
    have hgrow := equal_radius_arc_strict_order hquad₁ (hData.1.trans hps.symm)
    have hquad₂ := cyclic_strict_convex_quad_offsets S.convex x
      (a := 1) (b := 2) (c := soff) (d := zoff)
      (by decide) hs.1 hs.2.1 hzoffn
    have hg := equal_radius_arc_strict_order hquad₂ (by rw [← hzIndex]; exact hps.trans hpz.symm)
    exact not_lt_of_ge
      ((hb hs.1 hs.2.2.1).2.1
        (hg.trans_le (hb (hs.1.trans hs.2.1) hzoffn).1))
      (hData.2.2.symm.trans_lt hgrow)
  have hquad := erlv_x_p_u_z_strict_convex_quad S
  have hcompare := far_arc_strict_center_comparison hquad (by
    rw [hData.1, huIndex]
    simpa only [cyclicAdvance_zero] using
      (hb (Nat.zero_lt_of_lt huoff3) (hs.2.2.2.trans hs.2.2.1)).1)
  have hxzAdj := topThreeAdjacent_symm S.first_start_adjacent
  rcases strict_top_three_rank_slots S.classes hxzAdj
      (top_three_adjacent_of_strictly_longer S.classes hxzAdj hcompare) hcompare with h | h | h <;>
    try exact hpzNe h.2
  have hb := maximal_gap_tail_degree_bounds S hData.1 h.1 h.2
  exact high_degree_le_six_false S S.x
    ((d1_d3_opposite_sides_force_xu_top_two S.classes hquad hxzAdj hData.1 h.1 h.2).elim
      hb.1 (fun hu => (hb.2 hu).trans (by decide)))
