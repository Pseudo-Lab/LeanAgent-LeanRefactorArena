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
  induction h
  case const | op | fvar | bvar => constructor
  all_goals unfold LExpr.denote
  case abs hb ih =>
    split
    rename_i _ _ heq _ _
    cases heq
    exact .abs _ fun x => ih _
  case app hf ha ihf iha =>
    split
    rename_i _ _ _ ha' _
    cases HasTypeA_unique ha' ha
    exact .app _ (ihf _) (iha _)
  case ite hc ht he ihc iht ihe =>
    split
    dsimp only
    split
    · rename_i hv
      exact .ite_true _ (hv ▸ ihc _) (iht _)
    · rename_i hv
      exact .ite_false _ (Bool.eq_false_iff.mpr hv ▸ ihc _) (ihe _)
  case eq h1 h2 ih1 ih2 =>
    split
    rename_i _ _ _ h1' _ _
    cases HasTypeA_unique h1' h1
    dsimp only
    cases Classical.propDecidable _ with
    | isFalse hv => exact .eq_false _ (ih1 _) (ih2 _) hv
    | isTrue hv => exact .eq_true _ (ih1 _) (hv ▸ ih2 _)
  case quant htr hb ihtr ih =>
    split
    dsimp only
    split <;> cases Classical.propDecidable _
    next hv =>
      rcases Classical.not_forall.mp hv with ⟨w, hw⟩
      exact .quant_all_false _ w (Bool.eq_false_iff.mpr hw ▸ ih _)
    next hv => exact .quant_all_true _ fun x => hv x ▸ ih _
    next hv => exact .quant_exist_false _ fun x => Bool.eq_false_iff.mpr (fun hp => hv ⟨x, hp⟩) ▸ ih _
    next hv =>
      rcases hv with ⟨w, hw⟩
      exact .quant_exist_true _ w (hw ▸ ih _)
