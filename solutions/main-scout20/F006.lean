theorem liftBVars_denote
    {e : LExpr T.mono} {τ : LMonoTy}
    {Δ₁ Δ_insert Δ_outer : List LMonoTy}
    (h_orig : LExpr.HasTypeA (Δ₁ ++ Δ_outer) e τ)
    (h_lifted : LExpr.HasTypeA (Δ₁ ++ (Δ_insert ++ Δ_outer)) (LExpr.liftBVars Δ_insert.length e Δ₁.length) τ)
    (bv₁ : BVarVal tcInterp vt Δ₁)
    (bv_insert : BVarVal tcInterp vt Δ_insert)
    (bv_outer : BVarVal tcInterp vt Δ_outer)
    : LExpr.denote tcInterp opInterp fvarVal vt (HList.append bv₁ (HList.append bv_insert bv_outer))
        (LExpr.liftBVars Δ_insert.length e Δ₁.length) τ h_lifted =
      LExpr.denote tcInterp opInterp fvarVal vt (HList.append bv₁ bv_outer) e τ h_orig := by
  have liftTy {Δ : List LMonoTy} {a : LExpr T.mono} {t : LMonoTy}
      (h : LExpr.HasTypeA (Δ ++ Δ_outer) a t) :
      LExpr.HasTypeA (Δ ++ (Δ_insert ++ Δ_outer)) (LExpr.liftBVars Δ_insert.length a Δ.length) t := by
    simpa only [LExpr.HasTypeA_iff_typeCheck, ← List.append_assoc, liftBVars_typeCheck] using h
  induction e generalizing Δ₁ bv₁ τ <;> simp only [LExpr.liftBVars] at h_lifted ⊢
  case const => rfl
  case op m o ty => cases h_orig; rfl
  case fvar m name ty => cases h_orig; rfl
  case bvar m i =>
    by_cases hg : Δ₁.length ≤ i <;> simp only [hg, ↓reduceIte] at h_lifted ⊢
    all_goals rw [denote_bvar _ _ _ _ _ h_lifted, denote_bvar _ _ _ _ _ h_orig]
    · have ho := HasTypeA.bvar_inv h_orig
      rw [List.getElem?_append_right hg] at ho
      have hm := HasTypeA.bvar_inv h_lifted
      rw [List.getElem?_append_right (by omega : Δ₁.length ≤ i + Δ_insert.length)] at hm
      have hi : i + Δ_insert.length - Δ₁.length - Δ_insert.length = i - Δ₁.length := by omega
      rw [HList.get_append_right bv₁ (bv_insert.append bv_outer) _ _ hm (by omega),
        HList.get_append_right bv_insert bv_outer _ hm (by simpa only [hi] using ho) (by omega),
        HList.get_append_right bv₁ bv_outer _ _ ho hg]
      simp only [hi]
    · have hp := HasTypeA.bvar_inv h_orig
      rw [List.getElem?_append_left (by omega : i < Δ₁.length)] at hp
      rw [HList.get_append_left bv₁ (bv_insert.append bv_outer) i _ hp,
        HList.get_append_left bv₁ bv_outer i _ hp]
  case app m fn arg ih_fn ih_arg =>
    let ⟨aty, hf, ha⟩ := HasTypeA.app_inv h_orig
    rw [denote_app _ (liftTy hf) (liftTy ha) h_lifted, denote_app _ hf ha h_orig,
      ih_fn hf _ bv₁, ih_arg ha _ bv₁]
  case abs m name ty body ih =>
    cases h_orig with
    | abs hb =>
      have hl := liftTy (Δ := _ :: Δ₁) hb
      exact (denote_abs _ hl h_lifted).trans
        ((funext fun x => ih hb hl (.cons x bv₁)).trans (denote_abs _ hb (.abs hb)).symm)
  case ite m c t e ih_c ih_t ih_e =>
    let ⟨hc, ht, he⟩ := HasTypeA.ite_inv h_orig
    rw [denote_ite _ (liftTy hc) (liftTy ht) (liftTy he) h_lifted,
      denote_ite _ hc ht he h_orig,
      ih_c hc _ bv₁, ih_t ht _ bv₁, ih_e he _ bv₁]
  case eq m e1 e2 ih1 ih2 =>
    let ⟨ty, he, h1, h2⟩ := HasTypeA.eq_inv h_orig
    subst he
    have hh1 := ih1 h1 (liftTy h1) bv₁
    have hh2 := ih2 h2 (liftTy h2) bv₁
    apply Classical.byCases
    · intro heq
      rw [denote_eq_true _ h1 h2 h_orig heq]
      exact denote_eq_true _ _ _ h_lifted (by rw [hh1, hh2]; exact heq)
    · intro heq
      rw [denote_eq_false _ h1 h2 h_orig heq]
      exact denote_eq_false _ _ _ h_lifted (by rw [hh1, hh2]; exact heq)
  case quant m qk name qty tr body ih_tr ih_body =>
    cases h_orig with
    | quant ht hb =>
      have hl := liftTy (Δ := _ :: Δ₁) hb
      exact denote_quant_congr hl hb h_lifted (.quant ht hb) fun x =>
        ih_body hb hl (.cons x bv₁)
