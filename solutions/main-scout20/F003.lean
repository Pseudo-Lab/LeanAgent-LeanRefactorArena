theorem denote_Denotes
    {T : LExprParams}
    (tcInterp : TyConstrInterp)
    (opInterp : OpInterp tcInterp)
    (fvarVal : FreeVarVal T tcInterp)
    (vt : TyVarVal)
    {Δ : List LMonoTy}
    (bvarVal : BVarVal tcInterp vt Δ)
    (e : LExpr T.mono) (τ : LMonoTy)
    (h : LExpr.HasTypeA Δ e τ)
    : Denotes tcInterp opInterp fvarVal vt bvarVal e τ h
        (LExpr.denote tcInterp opInterp fvarVal vt bvarVal e τ h) := by
  classical
  induction e generalizing Δ τ with
  | abs _ _ ty body ih =>
    cases ty with
    | none => cases h
    | some aty =>
      rcases hi : HasTypeA.abs_inv h with ⟨rty, rfl, hb⟩
      simp only [LExpr.denote, hi]
      exact .abs bvarVal fun x => ih (.cons x bvarVal) _ hb
  | app _ fn arg ihf iha =>
    rcases hi : HasTypeA.app_inv h with ⟨aty, hf, ha⟩
    simp only [LExpr.denote, hi]
    exact .app bvarVal (ihf bvarVal _ hf) (iha bvarVal _ ha)
  | ite _ c t e' ihc iht ihe =>
    unfold LExpr.denote
    split
    rename_i _ hc ht he
    dsimp only
    split <;> rename_i hv
    · exact .ite_true bvarVal (hv ▸ ihc bvarVal _ hc) (iht bvarVal _ ht)
    · exact .ite_false bvarVal (Bool.eq_false_iff.mpr hv ▸ ihc bvarVal _ hc) (ihe bvarVal _ he)
  | eq _ e1 e2 ih1 ih2 =>
    rcases hi : HasTypeA.eq_inv h with ⟨ty, rfl, h1, h2⟩
    simp only [LExpr.denote, hi]
    cases hv : (Classical.propDecidable _).decide
    · exact .eq_false bvarVal (ih1 bvarVal _ h1) (ih2 bvarVal _ h2) (of_decide_eq_false hv)
    · exact .eq_true bvarVal (ih1 bvarVal _ h1) (of_decide_eq_true hv ▸ ih2 bvarVal _ h2)
  | quant _ k _ ty tr body ihtr ih =>
    cases ty with
    | none => cases h
    | some qty =>
      rcases hi : HasTypeA.quant_inv h with ⟨tt, rfl, ht, hb⟩
      simp only [LExpr.denote, hi]
      have ihv := fun x => ih (.cons x bvarVal) _ hb
      cases k <;> cases hv : (Classical.propDecidable _).decide
      · obtain ⟨w, hw⟩ := Classical.not_forall.mp (of_decide_eq_false hv)
        exact .quant_all_false bvarVal w (Bool.eq_false_iff.mpr hw ▸ ihv w)
      · exact .quant_all_true bvarVal fun x => of_decide_eq_true hv x ▸ ihv x
      · exact .quant_exist_false bvarVal fun x => Bool.eq_false_iff.mpr (not_exists.mp (of_decide_eq_false hv) x) ▸ ihv x
      · obtain ⟨w, hw⟩ := of_decide_eq_true hv
        exact .quant_exist_true bvarVal w (hw ▸ ihv w)
  | _ => cases h; constructor
