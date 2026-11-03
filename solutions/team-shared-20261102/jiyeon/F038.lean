theorem RS_jointAgreement_of_goodCoeffs_card_gt {deg : ℕ} {domain : ι ↪ F} {δ : ℝ≥0}
    (hδ : δ ≤ relativeUniqueDecodingRadius (ι := ι) (F := F)
      (C := ReedSolomon.code domain deg))
    (u : WordStack F (Fin 2) ι)
    (hS : (RS_goodCoeffs (deg := deg) (domain := domain) u δ).card > Fintype.card ι) :
    jointAgreement (C := ReedSolomon.code domain deg) (δ := δ) (W := u) := by
  classical
  set n : ℕ := Fintype.card ι
  set e : ℕ := Nat.floor (δ * n)
  set good : Finset F := RS_goodCoeffs (deg := deg) (domain := domain) u δ
  have hn_pos : 0 < n := by
    simp [n]
  have hgood_card : good.card > n := by
    simpa [good, n] using hS
  by_cases hdeg_zero : deg = 0
  · subst hdeg_zero
    let S0 : Finset ι := Finset.univ.filter (fun i => u 0 i = 0 ∧ u 1 i = 0)
    have hcode0_zero : ∀ w ∈ (ReedSolomon.code domain 0 : Set (ι → F)), w = 0 := by
      simp [ReedSolomon.code_zero]
    have hzero_card :
        ∀ z ∈ good,
          n - e ≤ (Finset.univ.filter (fun i : ι => u 0 i + z * u 1 i = 0)).card := by
      intro z hz
      have hz_rel : δᵣ(u 0 + z • u 1, ReedSolomon.code domain 0) ≤ δ := by
        exact (Finset.mem_filter.mp hz).2
      have hz_zero : δᵣ(u 0 + z • u 1, (0 : ι → F)) ≤ δ := by
        rw [Code.relCloseToCode_iff_relCloseToCodeword_of_minDist] at hz_rel
        rcases hz_rel with ⟨w, hwmem, hwdist⟩
        simpa [hcode0_zero w hwmem] using hwdist
      obtain ⟨Tz, hTz_card, hTz_agree⟩ :=
        (Code.relCloseToWord_iff_exists_agreementCols
          (u := u 0 + z • u 1) (v := (0 : ι → F)) (δ := δ)).1 hz_zero
      have hTz_sub :
          Tz ⊆ Finset.univ.filter (fun i : ι => u 0 i + z * u 1 i = 0) := by
        intro i hi
        simpa [Pi.add_apply, Pi.smul_apply, smul_eq_mul] using (hTz_agree i).1 hi
      exact le_trans hTz_card (Finset.card_le_card hTz_sub)
    have hsum_lower :
        good.card * (n - e) ≤
          good.sum (fun z => (Finset.univ.filter (fun i : ι => u 0 i + z * u 1 i = 0)).card) := by
      simpa [Nat.mul_comm, Nat.mul_left_comm, Nat.mul_assoc] using
        (Finset.sum_le_sum fun z hz => hzero_card z hz)
    have hsum_eq :
        good.sum (fun z => (Finset.univ.filter (fun i : ι => u 0 i + z * u 1 i = 0)).card)
          =
        Finset.univ.sum (fun i : ι =>
            (good.filter (fun z : F => u 0 i + z * u 1 i = 0)).card) := by
      simp only [Finset.card_filter]
      rw [Finset.sum_comm]
    have hcount_bound :
        ∀ i : ι,
          (good.filter (fun z : F => u 0 i + z * u 1 i = 0)).card
            ≤ if i ∈ S0 then good.card else 1 := by
      intro i
      by_cases hcommon : u 0 i = 0 ∧ u 1 i = 0
      · have hiS0 : i ∈ S0 := by
          simp [S0, hcommon]
        simp [hiS0, hcommon]
      · have hiS0 : i ∉ S0 := by
          simp [S0, hcommon]
        have hcard_le_one :
            (good.filter (fun z : F => u 0 i + z * u 1 i = 0)).card ≤ 1 := by
          apply Finset.card_le_one.mpr
          intro z1 hz1 z2 hz2
          have hz1_eq := (Finset.mem_filter.mp hz1).2
          have hz2_eq := (Finset.mem_filter.mp hz2).2
          by_cases hu1 : u 1 i = 0
          · exact False.elim (hcommon ⟨by simpa [hu1] using hz1_eq, hu1⟩)
          · exact mul_right_cancel₀ hu1 (add_left_cancel (hz1_eq.trans hz2_eq.symm))
        exact by simpa [hiS0] using hcard_le_one
    have hsum_upper :
        Finset.univ.sum (fun i : ι => (good.filter (fun z : F => u 0 i + z * u 1 i = 0)).card)
          ≤ S0.card * good.card + (n - S0.card) := by
      have hbound :
          Finset.univ.sum (fun i : ι =>
              (good.filter (fun z : F => u 0 i + z * u 1 i = 0)).card) ≤
            Finset.univ.sum (fun i : ι => if i ∈ S0 then good.card else 1) := Finset.sum_le_sum (fun i _ => hcount_bound i)
      have hsum_bound :
          Finset.univ.sum (fun i : ι => if i ∈ S0 then good.card else 1)
            = S0.card * good.card + (n - S0.card) := by
        have hc : (Finset.univ.filter fun x : ι => x ∉ S0) = S0ᶜ := by ext x; simp
        simp [Finset.sum_ite, hc, n, Finset.card_compl]
      exact le_trans hbound (le_of_eq hsum_bound)
    have hS0_card_nat : n - e ≤ S0.card := by
      have hmain :
          good.card * (n - e) ≤ S0.card * good.card + (n - S0.card) := by
        exact (hsum_lower.trans_eq hsum_eq).trans hsum_upper
      by_contra hS0_small
      have hm := Nat.mul_le_mul_left good.card (show S0.card + 1 ≤ n - e by omega)
      have hs := Nat.sub_le n S0.card
      nlinarith
    have hS0_card :
        (1 - δ) * (Fintype.card ι : ℝ≥0) ≤ (S0.card : ℝ≥0) := by
      exact (Code.relDist_floor_bound_iff_complement_bound n S0.card δ).mp hS0_card_nat
    refine ⟨S0, hS0_card, (fun _ => 0), ?_⟩
    intro k
    refine ⟨(ReedSolomon.code domain 0).zero_mem, ?_⟩
    intro i hi
    have hh := (Finset.mem_filter.mp hi).2
    fin_cases k
    · simpa using hh.1.symm
    · simpa using hh.2.symm
  · by_cases hdeg_le : deg ≤ n
    · letI : NeZero deg := ⟨hdeg_zero⟩
      have hBW : 2 * e < n - deg + 1 := by
        simpa [n, e] using
          (RS_BW_bound_of_le_relUDR (deg := deg) (domain := domain) (δ := δ) hdeg_le hδ)
      have hgood_pos := lt_trans hn_pos hgood_card
      let P_x : Finset F := Finset.univ.map domain
      let P_y : Finset F := good
      haveI : Nonempty P_x := by
        apply Finset.Nonempty.to_subtype
        simp [P_x]
      haveI : Nonempty P_y := by
        apply Finset.Nonempty.to_subtype
        exact Finset.card_pos.mp hgood_pos
      have evalY_natDegree_le_degreeX (z : F) (f : F[X][Y]) :
          (Polynomial.Bivariate.evalY z f).natDegree ≤ Polynomial.Bivariate.degreeX f := by
        rw [ps_eval_y_eq_eval_x_swap, ps_eval_x_eq_map]
        exact Polynomial.natDegree_map_le.trans (Polynomial.Bivariate.natDegreeY_swap f).le
      have evalX_eval_eq_evalY_eval (x z : F) (f : F[X][Y]) :
          (Polynomial.Bivariate.evalX x f).eval z = (Polynomial.Bivariate.evalY z f).eval x := by
        simpa [ps_eval_x_eq_map, Polynomial.Bivariate.evalY, Polynomial.eval_map] using
          (Polynomial.eval₂_at_apply (p := f) (f := Polynomial.evalRingHom x) (r := Polynomial.C z))
      obtain ⟨A, B, hA0, hA_degX, hA_degY, hB_degX, hB_degY, hAB⟩ :=
        RS_exists_bivariate_AB_of_goodCoeffs_card_gt
          (deg := deg) (domain := domain) (δ := δ) hdeg_le hδ u hS
      let quot_x : F → F[X] := fun z =>
        if hz : z ∈ good then
          Classical.choose (RS_exists_Pz_of_mem_goodCoeffs
            (deg := deg) (domain := domain) (δ := δ) u (z := z) hz)
        else 0
      let quot_y : F → F[X] := fun x =>
        Polynomial.C (u 0 (Function.invFun domain x)) +
          Polynomial.X * Polynomial.C (u 1 (Function.invFun domain x))
      have h_card_Px : (⟨n, hn_pos⟩ : ℕ+) ≤ P_x.card := by
        simp [P_x, n]
      have h_card_Py : (⟨good.card, hgood_pos⟩ : ℕ+) ≤ P_y.card := by
        simp [P_y]
      have h_quot_x :
          ∀ z ∈ P_y,
            (quot_x z).natDegree ≤ (e + deg - 1) - e ∧
              Polynomial.Bivariate.evalY z B = (quot_x z) * (Polynomial.Bivariate.evalY z A) := by
        intro z hz
        have hz_good : z ∈ good := by simpa [P_y] using hz
        let Pz : F[X] := Classical.choose
          (RS_exists_Pz_of_mem_goodCoeffs (deg := deg)
            (domain := domain) (δ := δ) u (z := z) hz_good)
        have hPz :
            Pz.natDegree < deg ∧
              Δ₀(u 0 + z • u 1, Pz.eval ∘ domain) ≤ e := by
          simpa [Pz, e] using
            (Classical.choose_spec
              (RS_exists_Pz_of_mem_goodCoeffs
                (deg := deg) (domain := domain) (δ := δ) u (z := z) hz_good))
        have hquot_def : quot_x z = Pz := by
          simp [quot_x, hz_good, Pz]
        refine ⟨?_, ?_⟩
        · rw [hquot_def]
          have hp : Pz.natDegree < deg := hPz.1
          omega
        · let Dz : F[X] := Polynomial.Bivariate.evalY z B - Pz * Polynomial.Bivariate.evalY z A
          obtain ⟨Tz, hTz_card, hTz_agree⟩ :=
            (Code.closeToWord_iff_exists_agreementCols
              (u := u 0 + z • u 1) (v := Pz.eval ∘ domain) (e := e)).1 hPz.2
          have hDz_eval :
              ∀ x ∈ Tz.image domain, Dz.eval x = 0 := by
            intro x hx
            rcases Finset.mem_image.mp hx with ⟨i, hiTz, rfl⟩
            have hi_eq : u 0 i + z * u 1 i = Pz.eval (domain i) := by
              simpa [Pi.add_apply, Pi.smul_apply, smul_eq_mul] using (hTz_agree i).1 hiTz
            have heval := congrArg (fun p : F[X] => p.eval z) (hAB i)
            simp only [Polynomial.eval_mul, Polynomial.eval_add, Polynomial.eval_C,
              Polynomial.eval_X, evalX_eval_eq_evalY_eval] at heval
            simpa only [Dz, Polynomial.eval_sub, Polynomial.eval_mul, sub_eq_zero, ← hi_eq] using heval
          have hDz_deg :
              Dz.natDegree ≤ e + deg - 1 := by
            apply (Polynomial.natDegree_sub_le _ _).trans
            apply max_le
            · exact (evalY_natDegree_le_degreeX z B).trans hB_degX
            · have hm := Polynomial.natDegree_mul_le (p := Pz) (q := Polynomial.Bivariate.evalY z A)
              have ha : (Polynomial.Bivariate.evalY z A).natDegree ≤ e :=
                (evalY_natDegree_le_degreeX z A).trans hA_degX
              have hp : Pz.natDegree < deg := hPz.1
              omega
          have hdeg_lt :
              Dz.natDegree < (Tz.image domain).card := by
            rw [Finset.card_image_of_injective _ domain.injective]
            omega
          have hDz_zero : Dz = 0 := by
            exact
              Polynomial.eq_zero_of_natDegree_lt_card_of_eval_eq_zero'
                (p := Dz) (s := Tz.image domain) hDz_eval hdeg_lt
          simpa [Dz, hquot_def, sub_eq_zero] using hDz_zero
      have h_quot_y :
          ∀ x ∈ P_x,
            (quot_y x).natDegree ≤ (e + 1) - e ∧
              Polynomial.Bivariate.evalX x B = (quot_y x) * (Polynomial.Bivariate.evalX x A) := by
        intro x hx
        rcases Finset.mem_map.mp hx with ⟨i, -, rfl⟩
        refine ⟨?_, ?_⟩
        · have hlin : (Polynomial.C (u 0 i) + Polynomial.X * Polynomial.C (u 1 i) : F[X]).natDegree ≤ 1 :=
            (Polynomial.natDegree_add_le _ _).trans
              (max_le (by simp) ((Polynomial.natDegree_mul_C_le
                (f := (Polynomial.X : F[X])) (a := u 1 i)).trans (by simp)))
          simpa [quot_y, Function.leftInverse_invFun domain.injective i] using hlin
        · simpa [quot_y, Function.leftInverse_invFun domain.injective i] using hAB i
      have h_le_1 :
          1 >
            ((((e + deg - 1 : ℕ) : ℚ) / ((⟨n, hn_pos⟩ : ℕ+) : ℚ)) +
              (((e + 1 : ℕ) : ℚ) / ((⟨good.card, hgood_pos⟩ : ℕ+) : ℚ))) := by
        change ((e + deg - 1 : ℕ) : ℚ) / (n : ℚ) + ((e + 1 : ℕ) : ℚ) / (good.card : ℚ) < 1
        have hnq : (0 : ℚ) < n := by exact_mod_cast hn_pos
        have hng : (n : ℚ) < good.card := by exact_mod_cast hgood_card
        have hf : ((e + 1 : ℕ) : ℚ) / good.card < ((e + 1 : ℕ) : ℚ) / n :=
          div_lt_div_of_pos_left (by positivity) hnq hng
        have he : (e + deg - 1) + (e + 1) ≤ n := by omega
        have hle : ((e + deg - 1 : ℕ) : ℚ) / n + ((e + 1 : ℕ) : ℚ) / n ≤ 1 := by
          rw [← add_div, div_le_iff₀ hnq, one_mul]
          exact_mod_cast he
        linarith
      obtain ⟨P, hBA, hP_degX, hP_degY, ⟨Q_x, hQx_card, hQx_sub, hQx_eval⟩, _⟩ :=
        polishchuk_spielman
          (a_x := e) (a_y := e) (b_x := e + deg - 1) (b_y := e + 1)
          (n_x := ⟨n, hn_pos⟩) (n_y := ⟨good.card, hgood_pos⟩)
          (h_bx_ge_ax := by omega) (h_by_ge_ay := by omega)
          (A := A) (B := B) hA0 hA_degX hB_degX hA_degY hB_degY
          P_x P_y quot_x quot_y h_card_Px h_card_Py h_quot_x h_quot_y h_le_1
      have hP_degX' : Polynomial.Bivariate.degreeX P ≤ deg - 1 := by
        omega
      let S0 : Finset ι := Q_x.preimage domain domain.injective.injOn
      have hS0_card_nat : n - e ≤ S0.card := by
        have himg : S0.map domain = Q_x := by
          ext x
          constructor
          · intro hx
            rcases Finset.mem_map.mp hx with ⟨i, hi, rfl⟩
            exact Finset.mem_preimage.mp hi
          · intro hx
            rcases Finset.mem_map.mp (hQx_sub hx) with ⟨i, -, rfl⟩
            exact Finset.mem_map.mpr ⟨i, Finset.mem_preimage.mpr hx, rfl⟩
        have hcard_eq : S0.card = Q_x.card := by
          calc
            S0.card = (S0.map domain).card := by symm; simp
            _ = Q_x.card := by simp [himg]
        exact by simpa [S0, hcard_eq, n, e] using hQx_card
      have hS0_card :
          (1 - δ) * (Fintype.card ι : ℝ≥0) ≤ (S0.card : ℝ≥0) := by
        exact (Code.relDist_floor_bound_iff_complement_bound n S0.card δ).mp hS0_card_nat
      have hv_mem (j : ℕ) : ((P.coeff j).eval ∘ domain) ∈ ReedSolomon.code domain deg := by
        have hcoeff_deg_nat := le_trans (Polynomial.Bivariate.coeff_natDegree_le_degreeX P j) hP_degX'
        have hcoeff_deg : (P.coeff j).degree < deg := by
          have hlt_nat := lt_of_le_of_lt hcoeff_deg_nat (Nat.pred_lt (NeZero.ne deg))
          exact lt_of_le_of_lt (Polynomial.degree_le_natDegree (p := P.coeff j))
            (by exact_mod_cast hlt_nat)
        refine ⟨P.coeff j, ?_, by ext i; rfl⟩
        simpa [Polynomial.mem_degreeLT] using hcoeff_deg
      refine ⟨S0, hS0_card, (fun k : Fin 2 => (P.coeff (k : ℕ)).eval ∘ domain), ?_⟩
      intro k
      refine ⟨hv_mem k, ?_⟩
      intro i hi
      have hc := congrArg (fun p : F[X] => p.coeff (k : ℕ)) (hQx_eval _ (Finset.mem_preimage.mp hi))
      fin_cases k <;> simpa [quot_y, Polynomial.Bivariate.evalX, Polynomial.coeff,
        Function.leftInverse_invFun domain.injective i] using hc
    · have htop : ReedSolomon.code domain deg = ⊤ := by
        apply Submodule.eq_top_of_finrank_eq
        simpa [LinearCode.dim] using
          (ReedSolomon.dim_eq_card_of_lt (α := domain) (Nat.lt_of_not_ge hdeg_le))
      refine ⟨Finset.univ, by simp, u, ?_⟩
      intro k
      exact ⟨by simp [htop], fun i _ => by simp⟩
