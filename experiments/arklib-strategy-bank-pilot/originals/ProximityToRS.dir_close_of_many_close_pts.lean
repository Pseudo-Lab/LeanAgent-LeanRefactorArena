lemma dir_close_of_many_close_pts
    {deg : ℕ}
    {α : ι ↪ F} {e : ℕ} {u v : ι → F}
    (he : (e : ℚ≥0) < ‖(RScodeSet α deg)‖₀ / 3)
    (h_many : numberOfClosePts u v deg α e > ‖(RScodeSet α deg)‖₀) :
    Δ₀(v, ReedSolomon.code α deg) ≤ e := by
  classical
  set CRS : Submodule F (ι → F) := ReedSolomon.code α deg
  set C : Set (ι → F) := (CRS : Set (ι → F))
  -- Convert `e < dist/3` into the arithmetic inequality `3*e < dist`.
  have h3e_lt : 3 * e < ‖C‖₀ := by
    have h3pos : (0 : ℚ≥0) < 3 := by norm_num
    have h' : (3 : ℚ≥0) * (e : ℚ≥0) < (‖C‖₀ : ℚ≥0) := by
      have hmul0 := mul_lt_mul_of_pos_left (by simpa [C, CRS, RScodeSet] using he) h3pos
      have hmul :
          (3 : ℚ≥0) * (e : ℚ≥0) < (3 : ℚ≥0) * ((‖C‖₀ : ℚ≥0) / 3) := by
        simpa [mul_assoc] using hmul0
      have h3ne : (3 : ℚ≥0) ≠ 0 := by norm_num
      have h3mul : (3 : ℚ≥0) * (‖C‖₀ : ℚ≥0) / 3 = ‖C‖₀ := by simp [h3ne]
      have :
          (3 : ℚ≥0) * (‖C‖₀ : ℚ≥0) / 3 =
            (3 : ℚ≥0) * ((‖C‖₀ : ℚ≥0) / 3) := by
        simpa [mul_div_assoc] using
          (mul_div_assoc (3 : ℚ≥0) (‖C‖₀ : ℚ≥0) (3 : ℚ≥0))
      have h3mul' : (3 : ℚ≥0) * ((‖C‖₀ : ℚ≥0) / 3) = ‖C‖₀ := by
        simpa [this] using h3mul
      simpa [h3mul'] using hmul
    exact_mod_cast h'
  -- Convert the `closePtsOnAffineLine` count into a count of good scalars.
  let P : F → Prop := fun r ↦ Δ₀(u + r • v, C) ≤ e
  let R : Finset F := Finset.filter P Finset.univ
  have h_close_le_card : numberOfClosePts u v deg α e ≤ R.card := by
    -- Surjection from good `r` values onto close points on the line.
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
      intro x
      rcases
          (Affine.mem_affineLineAtOrigin_iff (F := F) (origin := u) (direction := v) x.1).1 x.2.1
        with ⟨r, hr⟩
      refine ⟨⟨r, ?_⟩, ?_⟩
      · simpa [P, C, hr] using x.2.2
      · ext i
        simpa [f] using congrArg (fun w ↦ w i) hr.symm
    have h_close_card :
        Fintype.card
            (closePtsOnAffineLine (F := F) (u := u) (v := v) (deg := deg) (α := α) (e := e))
          ≤ Fintype.card {r : F // P r} :=
      Fintype.card_le_of_surjective f hf_surj
    simpa [numberOfClosePts, Fintype.card_subtype, R, P] using h_close_card
  have hR_gt : R.card > ‖C‖₀ := by
    have h_many' : numberOfClosePts u v deg α e > ‖C‖₀ := by
      simpa [C, CRS, RScodeSet] using h_many
    exact lt_of_lt_of_le h_many' h_close_le_card
  -- Work with the subtype of good scalars.
  let RS : Type := {r : F // r ∈ R}
  have hRS_card : Fintype.card RS = R.card := by
    classical
    simp [RS]
  have hRS_gt : Fintype.card RS > ‖C‖₀ := by simpa [hRS_card] using hR_gt
  -- Pick two distinct good scalars.
  have hdist_pos : 0 < ‖C‖₀ := by
    exact lt_of_le_of_lt (Nat.zero_le (3 * e)) h3e_lt
  have hRS_one_lt : 1 < Fintype.card RS := by
    have : 1 ≤ ‖C‖₀ := Nat.succ_le_of_lt hdist_pos
    exact lt_of_le_of_lt this hRS_gt
  have huniv_one_lt : 1 < (Finset.univ : Finset RS).card := by
    simpa [Finset.card_univ] using hRS_one_lt
  obtain ⟨r0, -, r1, -, hr01⟩ := Finset.one_lt_card.mp huniv_one_lt
  -- Define codewords and disagreement sets for each good scalar.
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
  -- The direction codeword `w`.
  have hr10 : (r1.1 - r0.1) ≠ 0 := sub_ne_zero.mpr (by
    intro h
    apply hr01
    ext
    exact h.symm)
  let w : ι → F := (r1.1 - r0.1)⁻¹ • (c r1 - c r0)
  have hw_mem : w ∈ CRS := by
    have hc1 : c r1 ∈ CRS := by simpa [C, CRS] using hc_mem r1
    have hc0 : c r0 ∈ CRS := by simpa [C, CRS] using hc_mem r0
    exact Submodule.smul_mem CRS _ (Submodule.sub_mem CRS hc1 hc0)
  have hv_eq_w_of_notin (j : ι) (hj0 : j ∉ E r0) (hj1 : j ∉ E r1) : v j = w j := by
    have h1 : (u + r1.1 • v) j = c r1 j := hE_agree r1 j hj1
    have h0 : (u + r0.1 • v) j = c r0 j := hE_agree r0 j hj0
    have hdiff : (r1.1 - r0.1) * v j = c r1 j - c r0 j := by
      have hsub : (u + r1.1 • v) j - (u + r0.1 • v) j = c r1 j - c r0 j := by
        simp [h1, h0]
      have hdiff' : r1.1 * v j - r0.1 * v j = c r1 j - c r0 j := by
        simpa [Pi.add_apply, Pi.smul_apply] using hsub
      simpa [sub_mul] using hdiff'
    calc
      v j = (r1.1 - r0.1)⁻¹ * ((r1.1 - r0.1) * v j) := by simp [hr10]
      _   = (r1.1 - r0.1)⁻¹ * (c r1 j - c r0 j) := by simp [hdiff]
      _   = w j := by simp [w, Pi.smul_apply, Pi.sub_apply]
  -- Define the base codeword so that `c r = cBase + r•w`.
  let cBase : ι → F := c r0 - r0.1 • w
  have hcBase_mem : cBase ∈ CRS := by
    have hc0 : c r0 ∈ CRS := by simpa [C, CRS] using hc_mem r0
    exact Submodule.sub_mem CRS hc0 (Submodule.smul_mem CRS _ hw_mem)
  -- Rewrite each decoded codeword in affine form and show agreement outside its disagreement set.
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
        have hcr : c r ∈ CRS := by simpa [C, CRS] using hc_mem r
        have hc0 : c r0 ∈ CRS := by simpa [C, CRS] using hc_mem r0
        exact Submodule.smul_mem CRS _ (Submodule.sub_mem CRS hcr hc0)
      have hw0r_eq : w0r = w := by
        apply Code.eq_of_lt_dist (C := C)
        · exact hw0r_mem
        · exact hw_mem
        · have hdist : Δ₀(w0r, w) ≤ (E r0 ∪ E r1 ∪ E r).card := by
            refine hamming_dist_le_of_subset_disagree (ι := ι) (u := w0r) (v := w)
              (D := E r0 ∪ E r1 ∪ E r) ?_
            intro i hi
            by_contra hiU
            have hi0 : i ∉ E r0 := by
              intro hi0
              apply hiU
              exact Finset.mem_union.2 (Or.inl (Finset.mem_union.2 (Or.inl hi0)))
            have hi1 : i ∉ E r1 := by
              intro hi1
              apply hiU
              exact Finset.mem_union.2 (Or.inl (Finset.mem_union.2 (Or.inr hi1)))
            have hir : i ∉ E r := by
              intro hir
              apply hiU
              exact Finset.mem_union.2 (Or.inr hir)
            have hvw : v i = w i := hv_eq_w_of_notin (j := i) hi0 hi1
            have hv0r : v i = w0r i := by
              have hr_eq : (u + r.1 • v) i = c r i := hE_agree r i hir
              have hr0_eq : (u + r0.1 • v) i = c r0 i := hE_agree r0 i hi0
              have hdiff :
                  (r.1 - r0.1) * v i = c r i - c r0 i := by
                have : (u + r.1 • v) i - (u + r0.1 • v) i = c r i - c r0 i := by
                  simp [hr_eq, hr0_eq]
                have hdiff' : r.1 * v i - r0.1 * v i = c r i - c r0 i := by
                  simpa [Pi.add_apply, Pi.smul_apply] using
                    (by simpa [Pi.add_apply, Pi.smul_apply] using this)
                simpa [sub_mul] using hdiff'
              calc
                v i = (r.1 - r0.1)⁻¹ * ((r.1 - r0.1) * v i) := by simp [hneq]
                _ = (r.1 - r0.1)⁻¹ * (c r i - c r0 i) := by simp [hdiff]
                _ = w0r i := by simp [w0r, Pi.smul_apply, Pi.sub_apply]
            exact hi (hv0r.symm.trans hvw)
          have hcard_le : (E r0 ∪ E r1 ∪ E r).card ≤ 3 * e := by
            have h01 :
                (E r0 ∪ E r1).card ≤ (E r0).card + (E r1).card :=
              Finset.card_union_le _ _
            have hUnion : (E r0 ∪ E r1 ∪ E r).card ≤ (E r0 ∪ E r1).card + (E r).card :=
              Finset.card_union_le _ _
            have hUnion' :
                (E r0 ∪ E r1 ∪ E r).card ≤
                  (E r0).card + (E r1).card + (E r).card := by
              calc
                (E r0 ∪ E r1 ∪ E r).card ≤ (E r0 ∪ E r1).card + (E r).card := hUnion
                _ ≤ ((E r0).card + (E r1).card) + (E r).card := Nat.add_le_add_right h01 _
                _ = (E r0).card + (E r1).card + (E r).card := by omega
            have hE0 : (E r0).card ≤ e := hE_card r0
            have hE1 : (E r1).card ≤ e := hE_card r1
            have hEr : (E r).card ≤ e := hE_card r
            have hSum : (E r0).card + (E r1).card + (E r).card ≤ e + e + e :=
              Nat.add_le_add (Nat.add_le_add hE0 hE1) hEr
            have : (E r0 ∪ E r1 ∪ E r).card ≤ e + e + e := le_trans hUnion' hSum
            have : (E r0 ∪ E r1 ∪ E r).card ≤ 3 * e := by omega
            exact this
          have : Δ₀(w0r, w) ≤ 3 * e := le_trans hdist hcard_le
          exact lt_of_le_of_lt this h3e_lt
      have hdiff : c r - c r0 = (r.1 - r0.1) • w := by
        have hsmul : (r.1 - r0.1) • w0r = (r.1 - r0.1) • w := by simp [hw0r_eq]
        simpa [w0r, smul_smul, hneq] using hsmul
      ext i
      have hdiff_i : c r i - c r0 i = (r.1 - r0.1) * w i := by
        have := congrArg (fun f ↦ f i) hdiff
        simpa [Pi.sub_apply, Pi.smul_apply] using this
      have hcri : c r i = (r.1 - r0.1) * w i + c r0 i := (sub_eq_iff_eq_add).1 hdiff_i
      simp [hcri, cBase, Pi.add_apply, Pi.smul_apply, Pi.sub_apply]
      ring
  have h_line_eq (r : RS) (j : ι) (hj : j ∉ E r) :
      (u + r.1 • v) j = (cBase + r.1 • w) j := by
    have hu : (u + r.1 • v) j = c r j := hE_agree r j hj
    have hc : c r j = (cBase + r.1 • w) j := by
      simp [h_codeword_eq (r := r), Pi.add_apply, Pi.smul_apply]
    simpa [hc] using hu
  -- The global disagreement set where `u` or `v` fail to match `cBase`/`w`.
  let D : Finset ι := Finset.filter (fun j ↦ u j ≠ cBase j ∨ v j ≠ w j) Finset.univ
  have hD_card : D.card ≤ e := by
    -- For `j ∈ D`, at most one good scalar can avoid `E r` at coordinate `j`.
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
        have hr_eq : (u + r.1 • v) j = (cBase + r.1 • w) j := h_line_eq r j hr'
        have hs_eq : (u + s.1 • v) j = (cBase + s.1 • w) j := h_line_eq s j hs'
        have hrs_val : r.1 ≠ s.1 := by
          intro h
          apply hrs
          ext
          exact h
        -- Solve the two linear equations to get `u j = cBase j` and `v j = w j`.
        have hvw : v j = w j := by
          have hrj : u j + r.1 * v j = cBase j + r.1 * w j := by
            simpa [Pi.add_apply, Pi.smul_apply] using hr_eq
          have hsj : u j + s.1 * v j = cBase j + s.1 * w j := by
            simpa [Pi.add_apply, Pi.smul_apply] using hs_eq
          have hrj' : u j - cBase j = r.1 * (w j - v j) := by
            have h1 := congrArg (fun t ↦ t - cBase j) hrj
            have h1' : u j + r.1 * v j - cBase j = r.1 * w j := by
              simpa [sub_eq_add_neg, add_assoc, add_left_comm, add_comm] using h1
            have h2 := congrArg (fun t ↦ t - r.1 * v j) h1'
            have h2' : u j - cBase j = r.1 * w j - r.1 * v j := by
              simpa [sub_eq_add_neg, add_assoc, add_left_comm, add_comm] using h2
            simpa [mul_sub] using h2'
          have hsj' : u j - cBase j = s.1 * (w j - v j) := by
            have h1 := congrArg (fun t ↦ t - cBase j) hsj
            have h1' : u j + s.1 * v j - cBase j = s.1 * w j := by
              simpa [sub_eq_add_neg, add_assoc, add_left_comm, add_comm] using h1
            have h2 := congrArg (fun t ↦ t - s.1 * v j) h1'
            have h2' : u j - cBase j = s.1 * w j - s.1 * v j := by
              simpa [sub_eq_add_neg, add_assoc, add_left_comm, add_comm] using h2
            simpa [mul_sub] using h2'
          have hmul : r.1 * (w j - v j) = s.1 * (w j - v j) := Eq.trans hrj'.symm hsj'
          have hzero : (r.1 - s.1) * (w j - v j) = 0 := by
            have : r.1 * (w j - v j) - s.1 * (w j - v j) = 0 := sub_eq_zero.mpr hmul
            simpa [sub_mul] using this
          have hne : r.1 - s.1 ≠ 0 := sub_ne_zero.mpr hrs_val
          have : w j - v j = 0 := by
            have := mul_eq_zero.mp hzero
            rcases this with h | h
            · exact False.elim (hne h)
            · exact h
          exact (sub_eq_zero.mp this).symm
        have hu_eq : u j = cBase j := by
          have hrj : u j + r.1 * v j = cBase j + r.1 * w j := by
            simpa [Pi.add_apply, Pi.smul_apply] using hr_eq
          have : u j + r.1 * v j = cBase j + r.1 * v j := by simpa [hvw] using hrj
          exact add_right_cancel this
        have hjD : u j ≠ cBase j ∨ v j ≠ w j := by
          have : j ∈ D := hj
          have : u j ≠ cBase j ∨ v j ≠ w j := by simpa [D] using (Finset.mem_filter.mp this).2
          exact this
        cases hjD with
        | inl hu_ne => exact (hu_ne hu_eq).elim
        | inr hv_ne => exact (hv_ne hvw).elim
      have hclean :
          (Finset.filter (fun r : RS ↦ j ∈ E r) Finset.univ).card =
            Fintype.card RS - (Finset.filter (fun r : RS ↦ j ∉ E r) Finset.univ).card := by
        classical
        set a : ℕ := (Finset.filter (fun r : RS ↦ j ∈ E r) Finset.univ).card
        set b : ℕ := (Finset.filter (fun r : RS ↦ j ∉ E r) Finset.univ).card
        have hpart : a + b = Fintype.card RS := by
          simpa [a, b, Finset.card_univ, Nat.add_comm, Nat.add_left_comm, Nat.add_assoc] using
            (Finset.card_filter_add_card_filter_not (s := (Finset.univ : Finset RS))
              (p := fun r : RS ↦ j ∈ E r))
        have hab : a = Fintype.card RS - b := by
          -- Subtract `b` from both sides of `hpart`.
          have := congrArg (fun t ↦ t - b) hpart
          simpa [Nat.add_sub_cancel] using this
        simpa [a, b] using hab
      have h_err :
          (Finset.filter (fun r : RS ↦ j ∈ E r) Finset.univ).card ≥ Fintype.card RS - 1 := by
        have hle := hclean_le1
        have hsub :
            Fintype.card RS - (Finset.filter (fun r : RS ↦ j ∉ E r) Finset.univ).card ≥
              Fintype.card RS - 1 := by
          have : (Finset.filter (fun r : RS ↦ j ∉ E r) Finset.univ).card ≤ 1 := hle
          exact Nat.sub_le_sub_left this _
        simpa [hclean] using hsub
      exact h_err
    have h_pairs_le :
        (∑ j ∈ D, (Finset.filter (fun r : RS ↦ j ∈ E r) Finset.univ).card) ≤
          Fintype.card RS * e := by
      -- Each `E r` has size `≤ e`, so sum over `r` bounds the total incidence count.
      have h_pairs_le' :
          (∑ j ∈ (Finset.univ : Finset ι),
                (Finset.filter (fun r : RS ↦ j ∈ E r) Finset.univ).card) ≤
            Fintype.card RS * e := by
        classical
        -- Count pairs `(r,j)` with `j ∈ E r` in two ways.
        let pairs : Finset (Sigma (fun _ : RS ↦ ι)) :=
          Finset.filter (fun p : Sigma (fun _ : RS ↦ ι) ↦ p.2 ∈ E p.1) Finset.univ
        have h_pairs_ge :
            pairs.card =
              ∑ j ∈ (Finset.univ : Finset ι),
                (Finset.filter (fun r : RS ↦ j ∈ E r) Finset.univ).card := by
          classical
          -- Use fiberwise counting on `p ↦ p.2`.
          let f : (Sigma (fun _ : RS ↦ ι)) → ι := fun p ↦ p.2
          have hf :
              (pairs : Set (Sigma (fun _ : RS ↦ ι))).MapsTo f
                (Finset.univ : Finset ι) := by
            intro _ _; simp
          have hcard_fiber := Finset.card_eq_sum_card_fiberwise (f := f) (s := pairs)
            (t := (Finset.univ : Finset ι)) hf
          have hfiber (j : ι) :
              {p ∈ pairs | f p = j}.card =
                (Finset.filter (fun r : RS ↦ j ∈ E r) Finset.univ).card := by
            classical
            let emb : RS ↪ Sigma (fun _ : RS ↦ ι) :=
              ⟨fun r ↦ ⟨r, j⟩, by
                intro a b h
                simpa using congrArg Sigma.fst h⟩
            have :
                Finset.filter (fun p : Sigma (fun _ : RS ↦ ι) ↦ p.2 = j) pairs =
                  (Finset.filter (fun r : RS ↦ j ∈ E r) Finset.univ).map emb := by
              ext p
              rcases p with ⟨r, i⟩
              have h :
                  (i ∈ E r ∧ i = j) ↔ (j ∈ E r ∧ j = i) := by
                constructor
                · intro h
                  refine ⟨?_, h.2.symm⟩
                  simpa [h.2] using h.1
                · intro h
                  refine ⟨?_, h.2.symm⟩
                  simpa [h.2] using h.1
              simp [pairs, emb, h]
            have hmap :
                {p ∈ pairs | f p = j} =
                  Finset.filter (fun p : Sigma (fun _ : RS ↦ ι) ↦ p.2 = j) pairs := by
              ext p
              simp [f]
            simp [hmap, this]
          have hpairs_sum :
              pairs.card = ∑ j ∈ (Finset.univ : Finset ι),
                (Finset.filter (fun r : RS ↦ j ∈ E r) Finset.univ).card := by
            classical
            simpa [hfiber] using hcard_fiber
          simp [hpairs_sum]
        -- Bound `pairs.card` by summing `|E r|`.
        have h_pairs_card :
            pairs.card ≤ ∑ r : RS, (E r).card := by
          classical
          -- Fiberwise count on `p ↦ p.1`.
          let g : (Sigma (fun _ : RS ↦ ι)) → RS := fun p ↦ p.1
          have hg :
              (pairs : Set (Sigma (fun _ : RS ↦ ι))).MapsTo g
                (Finset.univ : Finset RS) := by
            intro _ _; simp
          have hcard_fiber := Finset.card_eq_sum_card_fiberwise (f := g) (s := pairs)
            (t := (Finset.univ : Finset RS)) hg
          have hfiber (r : RS) :
              {p ∈ pairs | g p = r}.card = (E r).card := by
            classical
            let emb : ι ↪ Sigma (fun _ : RS ↦ ι) :=
              ⟨fun j ↦ ⟨r, j⟩, by
                intro a b h
                simpa using congrArg Sigma.snd h⟩
            have :
                Finset.filter (fun p : Sigma (fun _ : RS ↦ ι) ↦ p.1 = r) pairs =
                  (E r).map emb := by
              ext p
              rcases p with ⟨r', i⟩
              by_cases hrr : r' = r
              · subst hrr
                simp [pairs, emb]
              · constructor
                · intro hp
                  exfalso
                  exact hrr (Finset.mem_filter.mp hp).2
                · intro hp
                  exfalso
                  rcases Finset.mem_map.1 hp with ⟨j, hj, hjp⟩
                  have : r = r' := congrArg Sigma.fst hjp
                  exact hrr this.symm
            have hmap :
                {p ∈ pairs | g p = r} =
                  Finset.filter (fun p : Sigma (fun _ : RS ↦ ι) ↦ p.1 = r) pairs := by
              ext p
              simp [g]
            simp [hmap, this]
          -- Replace the sum of fiber cards by `∑ r, |E r|`.
          have hpairs_sum :
              pairs.card = ∑ r ∈ (Finset.univ : Finset RS), (E r).card := by
            classical
            simpa [hfiber] using hcard_fiber
          -- Drop the membership binder.
          simp [hpairs_sum]
        have hsumE : (∑ r : RS, (E r).card) ≤ Fintype.card RS * e := by
          classical
          have : ∀ r : RS, (E r).card ≤ e := fun r ↦ hE_card r
          calc
            (∑ r : RS, (E r).card) ≤ ∑ r : RS, e := by
              exact Finset.sum_le_sum (by intro r _; exact this r)
            _ = Fintype.card RS * e := by
              simp [Finset.card_univ]
        have hpairs_le : pairs.card ≤ Fintype.card RS * e := le_trans h_pairs_card hsumE
        -- Rewrite the LHS using the alternate counting of `pairs`.
        simpa [h_pairs_ge] using hpairs_le
      -- Restricting the sum to `D` only decreases it.
      have hsum_le :
          (∑ j ∈ D, (Finset.filter (fun r : RS ↦ j ∈ E r) Finset.univ).card)
            ≤ ∑ j ∈ (Finset.univ : Finset ι),
              (Finset.filter (fun r : RS ↦ j ∈ E r) Finset.univ).card := by
        refine
          Finset.sum_le_sum_of_subset_of_nonneg (s := D) (t := (Finset.univ : Finset ι)) ?_ ?_
        · intro j hj
          simp
        · intro _ _ _
          exact Nat.zero_le _
      exact le_trans hsum_le h_pairs_le'
    have h_pairs_ge :
        (∑ j ∈ D, (Finset.filter (fun r : RS ↦ j ∈ E r) Finset.univ).card) ≥
          D.card * (Fintype.card RS - 1) := by
      classical
      -- Each term is at least `card RS - 1`.
      have hterm : ∀ j ∈ D,
          (Fintype.card RS - 1) ≤ (Finset.filter (fun r : RS ↦ j ∈ E r) Finset.univ).card :=
        fun j hj ↦ by simpa using (h_err_ge j hj)
      have := Finset.sum_le_sum hterm
      -- Rewrite the LHS as `D.card * (card RS - 1)`.
      simpa [Finset.sum_const_nat, Nat.mul_comm, Nat.mul_left_comm, Nat.mul_assoc] using this
    -- Conclude `D.card ≤ e` by arithmetic.
    by_contra hD_gt
    have hD_ge : e + 1 ≤ D.card := Nat.succ_le_of_lt (lt_of_not_ge hD_gt)
    have hRS_one_le : 1 ≤ Fintype.card RS := Nat.one_le_of_lt hRS_one_lt
    have hdist_le : ‖C‖₀ ≤ Fintype.card RS - 1 := by
      have : ‖C‖₀ ≤ (Fintype.card RS).pred := Nat.le_pred_of_lt hRS_gt
      simpa [Nat.pred_eq_sub_one] using this
    have h3e_lt_RS : 3 * e < Fintype.card RS - 1 := lt_of_lt_of_le h3e_lt hdist_le
    have he_le_3e : e ≤ 3 * e := Nat.le_mul_of_pos_left (n := 3) e (by decide)
    have he_lt_RS : e < Fintype.card RS - 1 := lt_of_le_of_lt he_le_3e h3e_lt_RS
    have hmul_lt : Fintype.card RS * e < (e + 1) * (Fintype.card RS - 1) := by
      have hmulRS : e * (Fintype.card RS) = e * (Fintype.card RS - 1) + e := by
        have h :
            (Fintype.card RS) = Fintype.card RS - 1 + 1 := (Nat.sub_add_cancel hRS_one_le).symm
        rw [h]
        simp [Nat.mul_add]
      have hmulS :
          (e + 1) * (Fintype.card RS - 1) =
            e * (Fintype.card RS - 1) + (Fintype.card RS - 1) := by
        rw [Nat.add_one]
        simpa using Nat.succ_mul e (Fintype.card RS - 1)
      have hlt :
          e * (Fintype.card RS - 1) + e <
            e * (Fintype.card RS - 1) + (Fintype.card RS - 1) :=
        Nat.add_lt_add_left he_lt_RS _
      have : e * (Fintype.card RS) < (e + 1) * (Fintype.card RS - 1) := by
        have hlt' :
            e * (Fintype.card RS - 1) + e < (e + 1) * (Fintype.card RS - 1) := by
          simpa [hmulS] using hlt
        simpa [hmulRS] using hlt'
      simpa [Nat.mul_comm] using this
    have hle : (e + 1) * (Fintype.card RS - 1) ≤ Fintype.card RS * e := by
      have h1 : (e + 1) * (Fintype.card RS - 1) ≤ D.card * (Fintype.card RS - 1) :=
        Nat.mul_le_mul_right _ hD_ge
      have h2 : D.card * (Fintype.card RS - 1) ≤ Fintype.card RS * e := by
        exact le_trans h_pairs_ge h_pairs_le
      exact le_trans h1 h2
    exact (not_lt_of_ge hle) hmul_lt
  -- Use `D` to show the direction is `e`-close to a codeword.
  have hdist_vw : Δ₀(v, w) ≤ D.card := by
    refine hamming_dist_le_of_subset_disagree (ι := ι) (u := v) (v := w) (D := D) ?_
    intro j hj
    exact Finset.mem_filter.mpr ⟨Finset.mem_univ j, Or.inr hj⟩
  have hmem : w ∈ CRS := hw_mem
  have : Δ₀(v, CRS) ≤ e := by
    exact le_trans
      (Code.distFromCode_le_dist_to_mem (C := (CRS : Set (ι → F))) (u := v) (v := w)
        (by simpa [C] using hmem))
      (by
        exact_mod_cast le_trans hdist_vw hD_card)
  simpa [CRS] using this