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
    cases h₁ with
    | app hf ha =>
      have hf' := transfer h_lc.1 hf
      have ha' := transfer h_lc.2 ha
      rw [denote_app _ hf ha _, denote_app _ hf' ha' h₂,
        ih_fn h_lc.1 hf hf' bv₁, ih_arg h_lc.2 ha ha' bv₁]
  case ite m c t e ih_c ih_t ih_e =>
    cases h₁ with
    | ite hc ht he =>
      have hc' := transfer h_lc.1.1 hc
      have ht' := transfer h_lc.1.2 ht
      have he' := transfer h_lc.2 he
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
      · rw [denote_eq_true _ ha hc _ heq,
          denote_eq_true _ ha' hc' h₂ (by rwa [← he1, ← he2])]
      · rw [denote_eq_false _ ha hc _ heq,
          denote_eq_false _ ha' hc' h₂ (by rwa [← he1, ← he2])]
  case abs m name ty body ih =>
    cases h₁ with
    | abs hb =>
      have hb' := transfer (Γ := _ :: Δ₁) h_lc hb
      rw [denote_abs _ hb _, denote_abs _ hb' h₂]
      funext x
      exact ih (Δ₁ := _ :: Δ₁) h_lc hb hb' (.cons x bv₁)
  case quant m qk name ty tr body ih_tr ih =>
    cases h₁ with
    | quant ht hb =>
      have hb' := transfer (Γ := _ :: Δ₁) h_lc.2 hb
      exact denote_quant_congr hb hb' _ h₂ fun x =>
        ih (Δ₁ := _ :: Δ₁) h_lc.2 hb hb' (.cons x bv₁)
