theorem denote_replaceMetadata
    {T : LExprParams} [Inhabited T.mono.base.IDMeta]
    (tcInterp : TyConstrInterp)
    (opInterp : OpInterp tcInterp)
    (fvarVal : FreeVarVal T tcInterp)
    (vt : TyVarVal)
    {Δ : List LMonoTy}
    (bvarVal : BVarVal tcInterp vt Δ)
    {e₁ : LExpr T.mono} {τ : LMonoTy} (f : T.Metadata → NewMetadata)
    (h₁ : LExpr.HasTypeA Δ e₁ τ):
    let T' : LExprParams := ⟨NewMetadata, T.IDMeta⟩
    let opInterp' : OpInterp tcInterp := opInterp
    let fvarVal' : FreeVarVal T' tcInterp := fvarVal
    LExpr.denote tcInterp opInterp fvarVal vt bvarVal e₁ τ h₁ =
    LExpr.denote tcInterp opInterp' fvarVal' vt bvarVal (LExpr.replaceMetadata e₁ f) τ (replaceMetadata_HasTypeA f h₁) := by
  have hd := denote_Denotes _ opInterp fvarVal _ bvarVal _ _ h₁
  apply Denotes_denote
  generalize LExpr.denote .. = v at *
  induction hd
  case ite_false => apply Denotes.ite_false <;> assumption
  case quant_exist_true => apply Denotes.quant_exist_true <;> assumption
  case quant_exist_false => apply Denotes.quant_exist_false <;> assumption
  all_goals constructor <;> assumption
