lemma dir_close_of_many_close_pts
    {deg : ℕ}
    {α : ι ↪ F} {e : ℕ} {u v : ι → F}
    (he : (e : ℚ≥0) < ‖(RScodeSet α deg)‖₀ / 3)
    (h_many : numberOfClosePts u v deg α e > ‖(RScodeSet α deg)‖₀) :
    Δ₀(v, ReedSolomon.code α deg) ≤ e := by
  classical
  set CRS : Submodule F (ι → F) := ReedSolomon.code α deg
  set C : Set (ι → F) := (CRS : Set (ι → F))
  have h3e_lt : 3 * e < ‖C‖₀ := by
    have hq := (lt_div_iff₀ (by norm_num : (0 : ℚ≥0) < 3)).mp he
    have hq' : (3 : ℚ≥0) * (e : ℚ≥0) < (‖C‖₀ : ℚ≥0) := by
      simpa [C, CRS, RScodeSet, mul_comm] using hq
    exact_mod_cast hq'
  let P : F → Prop := fun r ↦ Δ₀(u + r • v, C) ≤ e
  let R : Finset F := Finset.filter P Finset.univ
  have h_close_le_card : numberOfClosePts u v deg α e ≤ R.card := by
    let f : {r : F // P r} → closePtsOnAffineLine (F := F) (u := u) (v := v)
        (deg := deg) (α := α) (e := e) :=
      fun r ↦
        ⟨u + r.1 • v,
          by
            refine ⟨?_, r.2⟩
            refine
              (Affine.mem_affineLineAtOrigin_iff (F := F) (origin := u) (direction := v) _).2 ?_
            exact ⟨r.1, rfl⟩⟩
    have hf_surj : Function.Surjective f := by
      rintro ⟨x, hx, hclose⟩
      obtain ⟨r, rfl⟩ :=
        (Affine.mem_affineLineAtOrigin_iff (F := F) (origin := u) (direction := v) x).1 hx
      exact ⟨⟨r, hclose⟩, rfl⟩
    simpa [numberOfClosePts, Fintype.card_subtype, R, P] using
      Fintype.card_le_of_surjective f hf_surj
  have hR_gt : R.card > ‖C‖₀ := by
    have h_many' : numberOfClosePts u v deg α e > ‖C‖₀ := by
      simpa [C, CRS, RScodeSet] using h_many
    exact lt_of_lt_of_le h_many' h_close_le_card
  let RS : Type := {r : F // r ∈ R}
  have hRS_card : Fintype.card RS = R.card := by
    classical
    simp [RS]
  have hRS_gt : Fintype.card RS > ‖C‖₀ := by simpa [hRS_card] using hR_gt
  have hRS_one_lt : 1 < Fintype.card RS := by omega
  obtain ⟨r0, r1, hr01⟩ := Fintype.one_lt_card_iff.mp hRS_one_lt
  have hP_of_mem (r : RS) : P r.1 := by
    have : r.1 ∈ R := r.2
    simpa [R, P, C] using (Finset.mem_filter.mp this).2
  have h_close_codeword (r : RS) : ∃ c ∈ C, Δ₀(u + r.1 • v, c) ≤ e :=
    (Code.closeToCode_iff_closeToCodeword_of_minDist (u := u + r.1 • v) (C := C) (e := e)).1
      (hP_of_mem r)
  choose c hc_mem hc_dist using h_close_codeword
  have h_disagree (r : RS) :
      ∃ D : Finset ι, D.card ≤ e ∧ ∀ j, j ∉ D → (u + r.1 • v) j = c r j :=
    (Code.closeToWord_iff_exists_possibleDisagreeCols (u := u + r.1 • v) (v := c r) (e := e)).1
      (hc_dist r)
  choose E hE_card hE_agree using h_disagree
  have hr10 : (r1.1 - r0.1) ≠ 0 := sub_ne_zero.mpr (by
    intro h
    apply hr01
    ext
    exact h.symm)
  let w : ι → F := (r1.1 - r0.1)⁻¹ • (c r1 - c r0)
  have hw_mem : w ∈ CRS := by
    exact CRS.smul_mem _ (CRS.sub_mem (hc_mem r1) (hc_mem r0))
  have hv_eq_w_of_notin (j : ι) (hj0 : j ∉ E r0) (hj1 : j ∉ E r1) : v j = w j := by
    have h1 := hE_agree r1 j hj1
    have h0 := hE_agree r0 j hj0
    change u j + r1.1 * v j = c r1 j at h1
    change u j + r0.1 * v j = c r0 j at h0
    change v j = (r1.1 - r0.1)⁻¹ * (c r1 j - c r0 j)
    rw [eq_inv_mul_iff_mul_eq₀ hr10]
    linear_combination h1 - h0
  let cBase : ι → F := c r0 - r0.1 • w
  have h_codeword_eq (r : RS) : c r = cBase + r.1 • w := by
    by_cases hr0 : r = r0
    · subst hr0
      simp [cBase]
    · have hneq : (r.1 - r0.1) ≠ 0 := sub_ne_zero.mpr (by
        intro h
        apply hr0
        ext
        exact h)
      let w0r : ι → F := (r.1 - r0.1)⁻¹ • (c r - c r0)
      have hw0r_mem : w0r ∈ CRS := by
        exact CRS.smul_mem _ (CRS.sub_mem (hc_mem r) (hc_mem r0))
      have hw0r_eq : w0r = w := by
        apply Code.eq_of_lt_dist (C := C)
        · exact hw0r_mem
        · exact hw_mem
        · have hdist : Δ₀(w0r, w) ≤ (E r0 ∪ E r1 ∪ E r).card := by
            refine hamming_dist_le_of_subset_disagree (ι := ι) (u := w0r) (v := w)
              (D := E r0 ∪ E r1 ∪ E r) ?_
            intro i hi
            by_contra hiU
            simp only [Finset.mem_union, not_or] at hiU
            rcases hiU with ⟨⟨hi0, hi1⟩, hir⟩
            have hvw : v i = w i := hv_eq_w_of_notin (j := i) hi0 hi1
            have hv0r : v i = w0r i := by
              have h1 := hE_agree r i hir
              have h0 := hE_agree r0 i hi0
              change u i + r.1 * v i = c r i at h1
              change u i + r0.1 * v i = c r0 i at h0
              change v i = (r.1 - r0.1)⁻¹ * (c r i - c r0 i)
              rw [eq_inv_mul_iff_mul_eq₀ hneq]
              linear_combination h1 - h0
            exact hi (hv0r.symm.trans hvw)
          have hcard_le : (E r0 ∪ E r1 ∪ E r).card ≤ 3 * e := by
            have h01 := Finset.card_union_le (E r0) (E r1)
            have hu := Finset.card_union_le (E r0 ∪ E r1) (E r)
            have h0 := hE_card r0
            have h1 := hE_card r1
            have hr := hE_card r
            omega
          have : Δ₀(w0r, w) ≤ 3 * e := le_trans hdist hcard_le
          exact lt_of_le_of_lt this h3e_lt
      have hdiff : c r - c r0 = (r.1 - r0.1) • w := by
        have hsmul : (r.1 - r0.1) • w0r = (r.1 - r0.1) • w := by simp [hw0r_eq]
        simpa [w0r, smul_smul, hneq] using hsmul
      ext i
      have hh := congrArg (fun f => f i) hdiff
      simp only [Pi.sub_apply, Pi.smul_apply, smul_eq_mul] at hh
      change c r i = c r0 i - r0.1 * w i + r.1 * w i
      linear_combination hh
  have h_line_eq (r : RS) (j : ι) (hj : j ∉ E r) :
      (u + r.1 • v) j = (cBase + r.1 • w) j := by
    simpa only [h_codeword_eq r] using hE_agree r j hj
  let D : Finset ι := Finset.filter (fun j ↦ u j ≠ cBase j ∨ v j ≠ w j) Finset.univ
  have hD_card : D.card ≤ e := by
    have h_err_ge (j : ι) (hj : j ∈ D) :
        (Finset.filter (fun r : RS ↦ j ∈ E r) Finset.univ).card ≥ Fintype.card RS - 1 := by
      have hclean_le1 : (Finset.filter (fun r : RS ↦ j ∉ E r) Finset.univ).card ≤ 1 := by
        by_contra hgt
        have hone :
            1 < (Finset.filter (fun r : RS ↦ j ∉ E r) Finset.univ).card :=
          lt_of_not_ge hgt
        rcases Finset.one_lt_card.mp hone with ⟨r, hr, s, hs, hrs⟩
        have hr' : j ∉ E r := (Finset.mem_filter.mp hr).2
        have hs' : j ∉ E s := (Finset.mem_filter.mp hs).2
        have hr_eq := h_line_eq r j hr'
        have hs_eq := h_line_eq s j hs'
        have hrs_val : r.1 ≠ s.1 := by
          intro h
          apply hrs
          ext
          exact h
        have hvw : v j = w j := by
          have hz : (r.1 - s.1) * (v j - w j) = 0 := by
            change u j + r.1 * v j = cBase j + r.1 * w j at hr_eq
            change u j + s.1 * v j = cBase j + s.1 * w j at hs_eq
            linear_combination hr_eq - hs_eq
          exact sub_eq_zero.mp ((mul_eq_zero.mp hz).resolve_left (sub_ne_zero.mpr hrs_val))
        have hu_eq : u j = cBase j := by
          have hrj : u j + r.1 * v j = cBase j + r.1 * w j := by
            simpa [Pi.add_apply, Pi.smul_apply] using hr_eq
          have : u j + r.1 * v j = cBase j + r.1 * v j := by simpa [hvw] using hrj
          exact add_right_cancel this
        exact (Finset.mem_filter.mp hj).2.elim (fun h => h hu_eq) (fun h => h hvw)
      have hp := Finset.card_filter_add_card_filter_not
        (s := (Finset.univ : Finset RS)) (p := fun r : RS => j ∈ E r)
      simp only [Finset.card_univ] at hp
      omega
    have h_pairs_le :
        (∑ j ∈ D, (Finset.filter (fun r : RS ↦ j ∈ E r) Finset.univ).card) ≤
          Fintype.card RS * e := by
      have h_pairs_le' :
          (∑ j ∈ (Finset.univ : Finset ι),
                (Finset.filter (fun r : RS ↦ j ∈ E r) Finset.univ).card) ≤
            Fintype.card RS * e := by
        calc
          _ = ∑ r : RS, (E r).card := by
            simp only [Finset.card_filter]
            rw [Finset.sum_comm]
            simp
          _ ≤ ∑ r : RS, e := Finset.sum_le_sum (fun r _ => hE_card r)
          _ = _ := by simp
      exact (Finset.sum_le_sum_of_subset (Finset.subset_univ D)).trans h_pairs_le'
    have h_pairs_ge :
        (∑ j ∈ D, (Finset.filter (fun r : RS ↦ j ∈ E r) Finset.univ).card) ≥
          D.card * (Fintype.card RS - 1) := by
      simpa [Finset.sum_const_nat, Nat.mul_comm] using Finset.sum_le_sum h_err_ge
    by_contra hD_gt
    have hd : e + 1 ≤ D.card := by omega
    have hp := Nat.mul_le_mul_right (Fintype.card RS - 1) hd
    have ht := h_pairs_ge.trans h_pairs_le
    have he' : e < Fintype.card RS - 1 := by omega
    have hc : Fintype.card RS = (Fintype.card RS - 1) + 1 := by omega
    nlinarith only [hp, ht, he', hc]
  have hdist_vw : Δ₀(v, w) ≤ D.card := by
    refine hamming_dist_le_of_subset_disagree (ι := ι) (u := v) (v := w) (D := D) ?_
    intro j hj
    exact Finset.mem_filter.mpr ⟨Finset.mem_univ j, Or.inr hj⟩
  have hmem := hw_mem
  have : Δ₀(v, CRS) ≤ e := le_trans
      (Code.distFromCode_le_dist_to_mem (C := (CRS : Set (ι → F))) (u := v) (v := w)
        (by simpa [C] using hmem))
      (by
        exact_mod_cast le_trans hdist_vw hD_card)
  simpa [CRS] using this
