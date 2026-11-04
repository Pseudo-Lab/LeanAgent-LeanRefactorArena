theorem RS_jointAgreement_of_goodCoeffs_card_gt {deg : ℕ} {domain : ι ↪ F} {δ : ℝ≥0}
    (hδ : δ ≤ relativeUniqueDecodingRadius (ι := ι) (F := F)
      (C := ReedSolomon.code domain deg))
    (u : WordStack F (Fin 2) ι)
    (hS : (RS_goodCoeffs (deg := deg) (domain := domain) u δ).card > Fintype.card ι) :
    jointAgreement (C := ReedSolomon.code domain deg) (δ := δ) (W := u) := by
  classical
  let n := Fintype.card ι
  let e := Nat.floor (δ * n)
  let good := RS_goodCoeffs (deg := deg) (domain := domain) u δ
  have hn : 0 < n := Fintype.card_pos
  have hg : n < good.card := hS
  by_cases hd : deg = 0
  · subst deg
    let bad := univ.image (fun i : ι => -(u 0 i) / u 1 i)
    have hb : bad.card ≤ n := card_image_le
    have hnot : ¬ good ⊆ bad := fun h => (not_le_of_gt hg) ((card_le_card h).trans hb)
    obtain ⟨z, hz, hzb⟩ := Finset.not_subset.mp hnot
    have hr : δᵣ(u 0 + z • u 1, ReedSolomon.code domain 0) ≤ δ :=
      (mem_filter.mp hz).2
    rw [Code.relCloseToCode_iff_relCloseToCodeword_of_minDist] at hr
    obtain ⟨w, hw, hr⟩ := hr
    have hw0 : w = 0 := by simpa [ReedSolomon.code_zero] using hw
    rw [hw0] at hr
    obtain ⟨T, hT, hTa⟩ := (Code.relCloseToWord_iff_exists_agreementCols
      (u := u 0 + z • u 1) (v := (0 : ι → F)) (δ := δ)).1 hr
    refine ⟨T, (Code.relDist_floor_bound_iff_complement_bound n T.card δ).mp hT,
      (0 : Fin 2 → ι → F), ?_⟩
    intro k
    refine ⟨(ReedSolomon.code domain 0).zero_mem, ?_⟩
    intro i hi
    have he : u 0 i + z * u 1 i = 0 := by
      simpa [Pi.add_apply, Pi.smul_apply, smul_eq_mul] using (hTa i).1 hi
    have h1 : u 1 i = 0 := by
      by_contra h1
      apply hzb
      have heq : z = -(u 0 i) / u 1 i := (eq_div_iff h1).mpr
        (eq_neg_of_add_eq_zero_left (by simpa only [add_comm] using he))
      exact mem_image.mpr ⟨i, mem_univ i, heq.symm⟩
    fin_cases k <;> simpa [h1, show u 0 i = 0 by simpa [h1] using he]
  · by_cases hdn : deg ≤ n
    · letI : NeZero deg := ⟨hd⟩
      have hBW : 2 * e < n - deg + 1 :=
        RS_BW_bound_of_le_relUDR (deg := deg) (domain := domain) hdn hδ
      have ⟨hed, hedeg, headd, hltdeg, hnat⟩ :
          (e + deg - 1) - e = deg - 1 ∧ e ≤ e + deg - 1 ∧
          (deg - 1) + e = e + deg - 1 ∧ e + deg - 1 < n - e ∧
          (e + deg - 1) + (e + 1) ≤ n := by omega
      have hgp : 0 < good.card := hn.trans hg
      have hfrac : (((e + deg - 1 : ℕ) : ℚ) / n + ((e + 1 : ℕ) : ℚ) / good.card) < 1 := by
        have hnq : (0 : ℚ) < n := Nat.cast_pos.mpr hn
        have hng : (n : ℚ) < good.card := Nat.cast_lt.mpr hg
        have hsmall : ((e + 1 : ℕ) : ℚ) / good.card < ((e + 1 : ℕ) : ℚ) / n :=
          div_lt_div_of_pos_left (by positivity) hnq hng
        have hsum : ((e + deg - 1 : ℕ) : ℚ) + ((e + 1 : ℕ) : ℚ) ≤ n := by
          exact_mod_cast hnat
        have hle : ((e + deg - 1 : ℕ) : ℚ) / n + ((e + 1 : ℕ) : ℚ) / n ≤ 1 := by
          rw [← add_div, div_le_iff₀ hnq]
          simpa using hsum
        exact (add_lt_add_right hsmall _).trans_le hle
      let Px := univ.map domain
      let Py := good
      haveI : Nonempty Px := by apply Finset.Nonempty.to_subtype; simp [Px]
      haveI : Nonempty Py := Finset.Nonempty.to_subtype (card_pos.mp hgp)
      have hEvalDeg (z : F) (f : F[X][Y]) :
          (evalY z f).natDegree ≤ degreeX f := by
        have he : evalY z f = ∑ j ∈ f.support, f.coeff j * (Polynomial.C z : F[X]) ^ j := by
          simp [evalY, eval_eq_sum, Polynomial.sum_def]
        rw [he]
        apply natDegree_sum_le_of_forall_le
        intro j hj
        exact (show (f.coeff j * (Polynomial.C z : F[X]) ^ j).natDegree ≤ (f.coeff j).natDegree by
          simpa [C_pow] using (natDegree_mul_C_le (f := f.coeff j) (a := z ^ j))).trans
            (coeff_natDegree_le_degreeX f j)
      have hcomm (x z : F) (f : F[X][Y]) :
          (evalX x f).eval z = (evalY z f).eval x := by
        rw [ps_eval_x_eq_map, eval_map]
        simpa [evalY] using (eval₂_at_apply (p := f) (f := evalRingHom x) (r := Polynomial.C z))
      obtain ⟨A, B, hA, hAx, hAy, hBx, hBy, hAB⟩ :=
        RS_exists_bivariate_AB_of_goodCoeffs_card_gt hdn hδ u hS
      let qx : F → F[X] := fun z => if hz : z ∈ good then
        Classical.choose (RS_exists_Pz_of_mem_goodCoeffs (deg := deg)
          (domain := domain) (δ := δ) u hz) else 0
      let qy : F → F[X] := fun x => Polynomial.C (u 0 (invFun domain x)) + Polynomial.X * Polynomial.C (u 1 (invFun domain x))
      have hqx : ∀ z ∈ Py, (qx z).natDegree ≤ (e + deg - 1) - e ∧
          evalY z B = qx z * evalY z A := by
        intro z hz
        have hz' : z ∈ good := hz
        have hp : (qx z).natDegree < deg ∧ Δ₀(u 0 + z • u 1, (qx z).eval ∘ domain) ≤ e := by
          simpa only [qx, dif_pos hz'] using Classical.choose_spec
            (RS_exists_Pz_of_mem_goodCoeffs (deg := deg) (domain := domain) (δ := δ) u hz')
        refine ⟨by rw [hed]; exact Nat.le_pred_of_lt hp.1, ?_⟩
        let D := evalY z B - qx z * evalY z A
        obtain ⟨T, hT, hTa⟩ := (Code.closeToWord_iff_exists_agreementCols
          (u := u 0 + z • u 1) (v := (qx z).eval ∘ domain) (e := e)).1 hp.2
        have hroot : ∀ x ∈ T.image domain, D.eval x = 0 := by
          intro x hx
          obtain ⟨i, hi, rfl⟩ := mem_image.mp hx
          have hi' : u 0 i + z * u 1 i = (qx z).eval (domain i) := by
            simpa [Pi.add_apply, Pi.smul_apply, smul_eq_mul] using (hTa i).1 hi
          have hab := congrArg (fun p : F[X] => p.eval z) (hAB i)
          simp only [eval_mul, eval_add, eval_C, eval_X] at hab
          rw [hcomm, hcomm, hi'] at hab
          simpa [D, eval_sub, eval_mul, sub_eq_zero] using hab
        have hD : D.natDegree ≤ e + deg - 1 := by
          apply (natDegree_sub_le _ _).trans
          apply max_le
          · exact (hEvalDeg z B).trans hBx
          · exact natDegree_mul_le.trans ((Nat.add_le_add (Nat.le_pred_of_lt hp.1)
              ((hEvalDeg z A).trans hAx)).trans_eq headd)
        have hlt : D.natDegree < (T.image domain).card := by
          rw [card_image_of_injective _ domain.injective]
          exact hD.trans_lt (hltdeg.trans_le hT)
        have hz0 := Polynomial.eq_zero_of_natDegree_lt_card_of_eval_eq_zero'
          (p := D) (s := T.image domain) hroot hlt
        exact sub_eq_zero.mp hz0
      have hqy : ∀ x ∈ Px, (qy x).natDegree ≤ (e + 1) - e ∧
          evalX x B = qy x * evalX x A := by
        intro x hx
        obtain ⟨i, -, rfl⟩ := mem_map.mp hx
        simp only [qy, leftInverse_invFun domain.injective i]
        refine ⟨?_, hAB i⟩
        have hlin : (Polynomial.X * Polynomial.C (u 1 i) : F[X]).natDegree ≤ 1 := by
          simpa using (natDegree_mul_C_le (f := (Polynomial.X : F[X])) (a := u 1 i))
        simpa using (natDegree_add_le (Polynomial.C (u 0 i)) (Polynomial.X * Polynomial.C (u 1 i))).trans (max_le (by simp) hlin)
      obtain ⟨P, hBA, hPx, hPy, ⟨Q, hQcard, hQsub, hQeval⟩, _⟩ :=
        polishchuk_spielman (a_x := e) (a_y := e) (b_x := e + deg - 1) (b_y := e + 1)
          (n_x := ⟨n, hn⟩) (n_y := ⟨good.card, hgp⟩)
          (h_bx_ge_ax := hedeg) (h_by_ge_ay := Nat.le_succ e)
          (A := A) (B := B) hA hAx hBx hAy hBy Px Py qx qy (by simp [Px, n]) (by simp [Py]) hqx hqy hfrac
      let S := Q.preimage domain domain.injective.injOn
      have himg : S.map domain = Q := by
        ext x
        constructor
        · intro hx
          obtain ⟨i, hi, rfl⟩ := mem_map.mp hx
          exact mem_preimage.mp hi
        · intro hx
          obtain ⟨i, -, rfl⟩ := mem_map.mp (hQsub hx)
          exact mem_map.mpr ⟨i, mem_preimage.mpr hx, rfl⟩
      have hc : S.card = Q.card := by rw [← himg, card_map]
      refine ⟨S, (Code.relDist_floor_bound_iff_complement_bound n S.card δ).mp
        (by simpa [hc] using hQcard), ?_⟩
      have hm (j : ℕ) : (P.coeff j).eval ∘ domain ∈ ReedSolomon.code domain deg := by
        have hj := (coeff_natDegree_le_degreeX P j).trans hPx
        rw [hed] at hj
        have hlt : (P.coeff j).natDegree < deg := hj.trans_lt (Nat.pred_lt hd)
        refine ⟨P.coeff j, ?_, by ext i; rfl⟩
        simpa [mem_degreeLT] using (degree_le_natDegree (p := P.coeff j)).trans_lt
          (show ((P.coeff j).natDegree : WithBot ℕ) < deg by exact_mod_cast hlt)
      use fun k : Fin 2 => (P.coeff k.val).eval ∘ domain
      intro k
      refine ⟨hm k.val, ?_⟩
      intro i hi
      have he := congrArg (fun p : F[X] => p.coeff k.val) (hQeval _ (mem_preimage.mp hi))
      fin_cases k <;> simpa [qy, ps_eval_x_eq_map, leftInverse_invFun domain.injective i] using he
    · have hmem (w : ι → F) : w ∈ ReedSolomon.code domain deg := by
        let p := Lagrange.interpolate univ domain w
        have hp : p.degree < (Fintype.card ι : WithBot ℕ) := by
          simpa [p] using (Lagrange.degree_interpolate_lt (s := univ) (v := domain) (r := w)
            (fun x _ y _ h => domain.injective h))
        refine ⟨p, ?_, ?_⟩
        · apply (mem_degreeLT).mpr
          exact hp.trans (by exact_mod_cast (Nat.lt_of_not_ge hdn))
        · ext i
          exact Lagrange.eval_interpolate_at_node (s := univ) (v := domain) (r := w)
            (fun x _ y _ h => domain.injective h) (mem_univ i)
      refine ⟨univ, by simp, u, ?_⟩
      intro k
      exact ⟨hmem (u k), fun i _ => by simp⟩
