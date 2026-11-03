lemma dir_close_of_many_close_pts
    {deg : ℕ}
    {α : ι ↪ F} {e : ℕ} {u v : ι → F}
    (he : (e : ℚ≥0) < ‖(RScodeSet α deg)‖₀ / 3)
    (h_many : numberOfClosePts u v deg α e > ‖(RScodeSet α deg)‖₀) :
    Δ₀(v, ReedSolomon.code α deg) ≤ e := by
  classical
  let CRS := ReedSolomon.code α deg
  let C : Set (ι → F) := CRS
  have h3e : 3 * e < ‖C‖₀ := by
    have h : (3 : ℚ≥0) * e < (‖C‖₀ : ℚ≥0) := by
      simpa [mul_comm] using
        (lt_div_iff₀ (by norm_num : (0 : ℚ≥0) < 3)).mp he
    exact_mod_cast h
  let P : F → Prop := fun r ↦ Δ₀(u + r • v, C) ≤ e
  let RS := {r : F // P r}
  have hcount : numberOfClosePts u v deg α e ≤ Fintype.card RS := by
    let f : RS → closePtsOnAffineLine (F := F) (u := u) (v := v)
        (deg := deg) (α := α) (e := e) := fun r ↦
      ⟨u + r.1 • v, (Affine.mem_affineLineAtOrigin_iff (F := F)
        (origin := u) (direction := v) _).2 ⟨r.1, rfl⟩, r.2⟩
    have hf : Function.Surjective f := by
      intro x
      obtain ⟨r, hr⟩ := (Affine.mem_affineLineAtOrigin_iff (F := F)
        (origin := u) (direction := v) x.1).1 x.2.1
      refine ⟨⟨r, ?_⟩, ?_⟩
      · simpa [P, hr] using x.2.2
      · apply Subtype.ext
        exact hr.symm
    exact Fintype.card_le_of_surjective f hf
  have hn : ‖C‖₀ < Fintype.card RS := lt_of_lt_of_le h_many hcount
  have hn1 : 1 < (Finset.univ : Finset RS).card := by
    simp only [Finset.card_univ]
    omega
  obtain ⟨r0, -, r1, -, hr01⟩ := Finset.one_lt_card.mp hn1
  have hclose (r : RS) : ∃ c ∈ C, Δ₀(u + r.1 • v, c) ≤ e :=
    (Code.closeToCode_iff_closeToCodeword_of_minDist
      (u := u + r.1 • v) (C := C) (e := e)).1 r.2
  choose c hc hd using hclose
  have herr (r : RS) : ∃ E : Finset ι, E.card ≤ e ∧
      ∀ j, j ∉ E → (u + r.1 • v) j = c r j :=
    (Code.closeToWord_iff_exists_possibleDisagreeCols
      (u := u + r.1 • v) (v := c r) (e := e)).1 (hd r)
  choose E hE hA using herr
  have diff (r s : RS) (j : ι) (hr : j ∉ E r) (hs : j ∉ E s) :
      (s.1 - r.1) * v j = c s j - c r j := by
    simpa [Pi.add_apply, Pi.smul_apply, sub_mul] using
      congrArg₂ (fun a b : F ↦ a - b) (hA s j hs) (hA r j hr)
  have slope (r s : RS) (hne : s.1 - r.1 ≠ 0) (j : ι)
      (hr : j ∉ E r) (hs : j ∉ E s) :
      v j = ((s.1 - r.1)⁻¹ • (c s - c r)) j := by
    simp [Pi.smul_apply, Pi.sub_apply, ← diff r s j hr hs, hne]
  have h10 : r1.1 - r0.1 ≠ 0 := sub_ne_zero.mpr (by
    intro h
    exact hr01 (Subtype.ext h.symm))
  let w := (r1.1 - r0.1)⁻¹ • (c r1 - c r0)
  have hw : w ∈ CRS := CRS.smul_mem _ (CRS.sub_mem (hc r1) (hc r0))
  have hcode (r : RS) : c r - c r0 = (r.1 - r0.1) • w := by
    apply Code.eq_of_lt_dist (C := C)
    · exact CRS.sub_mem (hc r) (hc r0)
    · exact CRS.smul_mem _ hw
    · have hdist : Δ₀(c r - c r0, (r.1 - r0.1) • w) ≤
          (E r0 ∪ E r1 ∪ E r).card := by
        apply hamming_dist_le_of_subset_disagree
        intro j hj
        by_contra hnot
        have hnot' : j ∉ E r0 ∧ j ∉ E r1 ∧ j ∉ E r := by
          simpa only [Finset.mem_union, not_or, and_assoc] using hnot
        have hv : v j = w j := slope r0 r1 h10 j hnot'.1 hnot'.2.1
        apply hj
        simpa only [Pi.sub_apply, Pi.smul_apply, smul_eq_mul, ← hv] using
          (diff r0 r j hnot'.1 hnot'.2.2).symm
      have hu := Finset.card_union_le (E r0) (E r1)
      have hu' := Finset.card_union_le (E r0 ∪ E r1) (E r)
      have h0 := hE r0
      have h1 := hE r1
      have hr := hE r
      omega
  let D := Finset.univ.filter (fun j ↦ v j ≠ w j)
  have hlow (j : ι) (hj : j ∈ D) :
      Fintype.card RS - 1 ≤ (Finset.univ.filter (fun r : RS ↦ j ∈ E r)).card := by
    have hclean : (Finset.univ.filter (fun r : RS ↦ j ∉ E r)).card ≤ 1 := by
      by_contra h
      obtain ⟨r, hr, s, hs, hrs⟩ := Finset.one_lt_card.mp (lt_of_not_ge h)
      have hne : s.1 - r.1 ≠ 0 := sub_ne_zero.mpr
        (fun h ↦ hrs (Subtype.ext h.symm))
      have hd : c s - c r = (s.1 - r.1) • w := by
        calc
          _ = (c s - c r0) - (c r - c r0) := (sub_sub_sub_cancel_right _ _ _).symm
          _ = _ := by rw [hcode s, hcode r, ← sub_smul, sub_sub_sub_cancel_right]
      have hv := slope r s hne j (Finset.mem_filter.mp hr).2 (Finset.mem_filter.mp hs).2
      rw [hd, smul_smul, inv_mul_cancel₀ hne, one_smul] at hv
      exact (Finset.mem_filter.mp hj).2 hv
    have hsum := Finset.card_filter_add_card_filter_not
      (s := (Finset.univ : Finset RS)) (p := fun r ↦ j ∈ E r)
    simp only [Finset.card_univ] at hsum
    omega
  have hupper : (∑ j ∈ D, (Finset.univ.filter (fun r : RS ↦ j ∈ E r)).card)
      ≤ Fintype.card RS * e := by
    calc
      _ ≤ ∑ j : ι, (Finset.univ.filter (fun r : RS ↦ j ∈ E r)).card := by
        apply Finset.sum_le_sum_of_subset_of_nonneg (Finset.subset_univ D)
        intro j _ _
        exact Nat.zero_le _
      _ = ∑ r : RS, (E r).card := by
        simp only [Finset.card_eq_sum_ones, Finset.sum_filter]
        rw [Finset.sum_comm]
        simp [← Finset.sum_filter]
      _ ≤ ∑ r : RS, e := Finset.sum_le_sum (fun r _ ↦ hE r)
      _ = _ := by simp
  have hlower : D.card * (Fintype.card RS - 1) ≤
      ∑ j ∈ D, (Finset.univ.filter (fun r : RS ↦ j ∈ E r)).card := by
    simpa using Finset.sum_le_sum hlow
  have hD : D.card ≤ e := by
    have hbound := le_trans hlower hupper
    have hnsub : Fintype.card RS = (Fintype.card RS - 1) + 1 := by omega
    have he' : e < Fintype.card RS - 1 := by omega
    by_contra h
    have hm := Nat.mul_le_mul_right (Fintype.card RS - 1) (show e + 1 ≤ D.card by omega)
    have hh := le_trans hm hbound
    rw [hnsub] at hh
    simp only [Nat.add_mul, Nat.one_mul] at hh
    rw [Nat.mul_comm e] at hh
    exact (not_le_of_gt he') (Nat.le_of_add_le_add_left hh)
  have hvw : Δ₀(v, w) ≤ D.card := by
    apply hamming_dist_le_of_subset_disagree
    intro j hj
    exact Finset.mem_filter.mpr ⟨Finset.mem_univ _, hj⟩
  exact le_trans (Code.distFromCode_le_dist_to_mem (C := C) (u := v) (v := w) hw)
    (by exact_mod_cast le_trans hvw hD)
