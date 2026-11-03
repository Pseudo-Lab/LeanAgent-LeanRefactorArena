theorem insertZero_nonadjacent_disjoint (J : PolygonalCircle) {p : Plane}
    (hp : p ∈ J.edgeSegment 0) (hp0 : p ≠ J.vertex 0) (hp1 : p ≠ J.vertex 1)
    (i j : ZMod (J.n + 1)) (hij : i ≠ j) (hprev : i ≠ j + 1)
    (hnext : j ≠ i + 1) :
    J.insertZeroEdgeSegment p i ∩ J.insertZeroEdgeSegment p j = ∅ := by
  wlog hle : i.val ≤ j.val generalizing i j
  · rw [Set.inter_comm]
    exact this j i hij.symm hnext hprev (by omega)
  have hi := ZMod.natCast_zmod_val i
  have hj := ZMod.natCast_zmod_val j
  have hgap : i.val + 1 < j.val := by
    have hne : i.val ≠ j.val := fun h => hij (ZMod.val_injective _ h)
    have hsucc : j.val ≠ i.val + 1 := by
      intro h
      apply hnext
      rw [← hi, ← hj, h, Nat.cast_add, Nat.cast_one]
    omega
  have hzero : i.val = 0 → j.val < J.n := by
    intro hz
    have hne : j.val ≠ J.n := by
      intro hn
      apply hprev
      rw [← hi, ← hj, hz, hn, Nat.cast_zero]
      simpa only [Nat.cast_add, Nat.cast_one] using
        (ZMod.natCast_self (J.n + 1)).symm
    have := j.val_lt
    omega
  suffices ordered : ∀ (m l : ℕ), l < J.n + 1 → m + 1 < l →
      (m = 0 → l < J.n) →
      Disjoint (J.insertZeroEdgeSegment p (m : ZMod (J.n + 1)))
        (J.insertZeroEdgeSegment p (l : ZMod (J.n + 1))) by
    apply Set.disjoint_iff_inter_eq_empty.mp
    simpa only [ZMod.natCast_zmod_val] using
      ordered i.val j.val j.val_lt hgap hzero
  clear i j hij hprev hnext hle hi hj hgap hzero
  let : Fact (1 < J.n) := ⟨lt_of_lt_of_le (by decide) J.three_le⟩
  have hz (k : ℕ) (hk : 1 < k) (hkn : k + 1 < J.n) :
      Disjoint (J.edgeSegment 0) (J.edgeSegment (k : ZMod J.n)) := by
    have hklt : k < J.n := lt_trans (Nat.lt_succ_self k) hkn
    apply Set.disjoint_iff_inter_eq_empty.mpr
    apply J.nonadjacent_disjoint <;> intro h <;>
      have hv := congrArg ZMod.val h <;>
      simp only [zero_add, ZMod.val_add, ZMod.val_zero,
        ZMod.val_natCast_of_lt hklt, ZMod.val_one,
        Nat.mod_eq_of_lt hkn] at hv <;> omega
  intro m l hl hgap hzero
  by_cases hm0 : m = 0
  · have hllt := hzero hm0
    rw [hm0, Nat.cast_zero, J.insertZeroEdgeSegment_zero,
      J.insertZeroEdgeSegment_middle p (by omega) hllt]
    by_cases hlast : l = J.n - 1
    · rw [hlast]
      exact J.disjoint_insertZero_first_previous hp hp0 hp1
    · exact (hz l (by omega) (by omega)).mono_left
        (J.insertZero_first_subset_edge_zero hp)
  · have hmpos : 0 < m := Nat.pos_of_ne_zero hm0
    have hmlt : m < J.n := by omega
    rw [J.insertZeroEdgeSegment_middle p hmpos hmlt]
    by_cases hln : l = J.n
    · rw [hln, J.insertZeroEdgeSegment_last]
      by_cases hm1 : m = 1
      · rw [hm1, Nat.cast_one]
        exact (J.disjoint_insertZero_last_next hp hp0 hp1).symm
      · exact ((hz m (by omega) (by omega)).mono_left
          (J.insertZero_last_subset_edge_zero hp)).symm
    · have hllt : l < J.n := by omega
      rw [J.insertZeroEdgeSegment_middle p (by omega) hllt]
      apply Set.disjoint_iff_inter_eq_empty.mpr
      apply J.nonadjacent_disjoint
      · intro h
        have := natCast_eq_natCast_of_lt hmlt hllt h
        omega
      · intro h
        have := natCast_eq_succ_of_pos_lt hmpos hmlt hllt h
        omega
      · intro h
        have := natCast_eq_succ_of_pos_lt (by omega : 0 < l) hllt hmlt h
        omega
