theorem denote_suffix_irrel
    {e : LExpr T.mono} {τ : LMonoTy}
    {Δ₁ : List LMonoTy} {Δ₂ Δ₂' : List LMonoTy}
    (h_lc : LExpr.lcAt Δ₁.length e = true)
    (h₁ : LExpr.HasTypeA (Δ₁ ++ Δ₂) e τ)
    (h₂ : LExpr.HasTypeA (Δ₁ ++ Δ₂') e τ)
    (bv₁ : BVarVal tcInterp vt Δ₁)
    (bv₂ : BVarVal tcInterp vt Δ₂)
    (bv₂' : BVarVal tcInterp vt Δ₂')
    : LExpr.denote tcInterp opInterp fvarVal vt (HList.append bv₁ bv₂) e τ h₁ =
      LExpr.denote tcInterp opInterp fvarVal vt (HList.append bv₁ bv₂') e τ h₂ := by
  have transfer {Γ : List LMonoTy} {a : LExpr T.mono} {σ : LMonoTy}
      (hc : LExpr.lcAt Γ.length a = true)
      (ht : LExpr.HasTypeA (Γ ++ Δ₂) a σ) :
      LExpr.HasTypeA (Γ ++ Δ₂') a σ := by
    apply LExpr.typeCheck_to_HasTypeA
    exact (typeCheck_of_lcAt_aux (Δ := Γ ++ Δ₂) (Δ' := Γ ++ Δ₂') hc
      (fun i hi => by rw [List.getElem?_append_left hi, List.getElem?_append_left hi])).symm.trans
      (LExpr.HasTypeA_to_typeCheck ht)
  induction e generalizing Δ₁ τ <;> simp only [LExpr.lcAt, Bool.and_eq_true] at h_lc
  case const => rfl
  case op => cases h₁; rfl
  case fvar => cases h₁; rfl
  case bvar m i =>
    simp at h_lc
    rw [denote_bvar _ _ _ _ _ h₁, denote_bvar _ _ _ _ _ h₂]
    have hp : Δ₁[i]? = some τ := by
      have h := HasTypeA.bvar_inv h₁
      rwa [List.getElem?_append_left h_lc] at h
    rw [HList.get_append_left bv₁ bv₂ i (HasTypeA.bvar_inv h₁) hp,
      HList.get_append_left bv₁ bv₂' i (HasTypeA.bvar_inv h₂) hp]
  case app m fn arg ih_fn ih_arg =>
    obtain ⟨aty, hf, ha⟩ := HasTypeA.app_inv h₁
    have hf' := transfer h_lc.1 hf
    have ha' := transfer h_lc.2 ha
    exact (denote_app _ hf ha _).trans
      ((congr (ih_fn h_lc.1 hf hf' bv₁)
        (ih_arg h_lc.2 ha ha' bv₁)).trans (denote_app _ hf' ha' h₂).symm)
  case ite m c t e ih_c ih_t ih_e =>
    obtain ⟨hc, ht, he⟩ := HasTypeA.ite_inv h₁
    obtain ⟨hc', ht', he'⟩ := HasTypeA.ite_inv h₂
    rw [denote_ite _ hc ht he, denote_ite _ hc' ht' he',
      ih_c h_lc.1.1 hc hc' bv₁, ih_t h_lc.1.2 ht ht' bv₁, ih_e h_lc.2 he he' bv₁]
  case eq m e1 e2 ih1 ih2 =>
    cases h₁ with
    | eq ha hc =>
      have ha' := transfer h_lc.1 ha
      have hc' := transfer h_lc.2 hc
      have he1 := ih1 h_lc.1 ha ha' bv₁
      have he2 := ih2 h_lc.2 hc hc' bv₁
      by_cases heq : LExpr.denote tcInterp opInterp fvarVal vt (HList.append bv₁ bv₂) e1 _ ha =
          LExpr.denote tcInterp opInterp fvarVal vt (HList.append bv₁ bv₂) e2 _ hc
      · exact (denote_eq_true _ ha hc _ heq).trans
          (denote_eq_true _ ha' hc' h₂ (he1.symm.trans (heq.trans he2))).symm
      · exact (denote_eq_false _ ha hc _ heq).trans
          (denote_eq_false _ ha' hc' h₂ (fun h => heq (he1.trans (h.trans he2.symm)))).symm
  case abs m name ty body ih =>
    cases h₁ with
    | abs hb =>
      have hb' := transfer (Γ := _ :: Δ₁) h_lc hb
      exact (denote_abs _ hb _).trans ((funext fun x =>
        ih (Δ₁ := _ :: Δ₁) h_lc hb hb' (.cons x bv₁)).trans (denote_abs _ hb' h₂).symm)
  case quant m qk name ty tr body ih_tr ih =>
    cases h₁ with
    | quant ht hb =>
      obtain ⟨_, _, _, hb'⟩ := HasTypeA.quant_inv h₂
      exact denote_quant_congr hb hb' _ h₂ fun x =>
        ih (Δ₁ := _ :: Δ₁) h_lc.2 hb hb' (.cons x bv₁)
