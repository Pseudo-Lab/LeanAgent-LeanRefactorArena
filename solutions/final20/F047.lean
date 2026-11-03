theorem insertZero_nonadjacent_disjoint (J : PolygonalCircle) {p : Plane}
    (hp : p ∈ J.edgeSegment 0) (hp0 : p ≠ J.vertex 0) (hp1 : p ≠ J.vertex 1)
    (i j : ZMod (J.n + 1)) (hij : i ≠ j) (hprev : i ≠ j + 1)
    (hnext : j ≠ i + 1) :
    J.insertZeroEdgeSegment p i ∩ J.insertZeroEdgeSegment p j = ∅ := by
  wlog hle : i.val ≤ j.val generalizing i j
  · rw [Set.inter_comm]
    exact this j i hij.symm hnext hprev (Nat.le_of_not_ge hle)
  let : Fact (1 < J.n) := ⟨lt_of_lt_of_le (by decide : 1 < 3) J.three_le⟩
  have old (k : ℕ) (hk1 : 1 < k) (hk : k + 1 < J.n) :
      J.edgeSegment 0 ∩ J.edgeSegment (k : ZMod J.n) = ∅ := by
    have hklt : k < J.n := lt_trans (Nat.lt_succ_self k) hk
    apply J.nonadjacent_disjoint
    · intro h
      apply (ne_of_lt (lt_trans Nat.zero_lt_one hk1))
      simpa only [ZMod.val_zero, ZMod.val_natCast_of_lt hklt] using congrArg ZMod.val h
    · intro h
      apply Nat.succ_ne_zero k
      simpa only [ZMod.val_zero, ZMod.val_add, ZMod.val_natCast_of_lt hklt,
        ZMod.val_one, Nat.mod_eq_of_lt hk] using congrArg ZMod.val h.symm
    · intro h
      apply (ne_of_gt hk1)
      simpa only [zero_add, ZMod.val_natCast_of_lt hklt, ZMod.val_one] using congrArg ZMod.val h
  let m := i.val
  let l := j.val
  have hl : l < J.n + 1 := j.val_lt
  have hi : (m : ZMod (J.n + 1)) = i := ZMod.natCast_zmod_val i
  have hj : (l : ZMod (J.n + 1)) = j := ZMod.natCast_zmod_val j
  have hml : m < l := lt_of_le_of_ne hle (fun h => hij (ZMod.val_injective _ h))
  simp only [← hi, ← hj] at hprev hnext ⊢
  have hgap : m + 1 < l := by
    apply lt_of_le_of_ne (Nat.succ_le_of_lt hml)
    intro h
    apply hnext
    simp only [← h, Nat.cast_succ]
  by_cases hm0 : m = 0
  · have hend : l ≠ J.n := by
      intro hln
      apply hprev
      simpa only [hm0, hln, Nat.cast_zero, Nat.cast_add, Nat.cast_one] using
        (ZMod.natCast_self (J.n + 1)).symm
    have hllt : l < J.n := lt_of_le_of_ne (Nat.le_of_lt_succ hl) hend
    simp only [hm0, Nat.cast_zero, J.insertZeroEdgeSegment_zero,
      J.insertZeroEdgeSegment_middle p (Nat.zero_lt_of_lt hml) hllt]
    by_cases hlast : l + 1 = J.n
    · rw [Nat.eq_sub_of_add_eq hlast]
      exact Set.disjoint_iff_inter_eq_empty.mp
        (J.disjoint_insertZero_first_previous hp hp0 hp1)
    exact Set.eq_empty_of_subset_empty
      ((Set.inter_subset_inter_left _ (J.insertZero_first_subset_edge_zero hp)).trans_eq
        (old l (by simpa only [hm0, Nat.zero_add] using hgap)
          (lt_of_le_of_ne (Nat.succ_le_of_lt hllt) hlast)))
  have hmpos : 0 < m := Nat.pos_of_ne_zero hm0
  have hmlt : m < J.n := lt_of_lt_of_le hml (Nat.le_of_lt_succ hl)
  simp only [J.insertZeroEdgeSegment_middle p hmpos hmlt]
  by_cases hln : l = J.n
  · simp only [hln, J.insertZeroEdgeSegment_last]
    by_cases hm1 : m = 1
    · simp only [hm1, Nat.cast_one]
      exact Set.disjoint_iff_inter_eq_empty.mp
        (J.disjoint_insertZero_last_next hp hp0 hp1).symm
    rw [Set.inter_comm]
    exact Set.eq_empty_of_subset_empty
      ((Set.inter_subset_inter_left _ (J.insertZero_last_subset_edge_zero hp)).trans_eq
        (old m (lt_of_le_of_ne hmpos (Ne.symm hm1)) (hln ▸ hgap)))
  have hlpos : 0 < l := Nat.zero_lt_of_lt hml
  have hllt : l < J.n := lt_of_le_of_ne (Nat.le_of_lt_succ hl) hln
  simp only [J.insertZeroEdgeSegment_middle p hlpos hllt]
  apply J.nonadjacent_disjoint
  · intro h
    exact (ne_of_lt hml) (natCast_eq_natCast_of_lt hmlt hllt h)
  · intro h
    exact (ne_of_lt (lt_trans hml (Nat.lt_succ_self l)))
      (natCast_eq_succ_of_pos_lt hmpos hmlt hllt h)
  · intro h
    exact (ne_of_gt hgap) (natCast_eq_succ_of_pos_lt hlpos hllt hmlt h)
