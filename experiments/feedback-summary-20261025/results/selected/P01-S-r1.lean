open OldExpressions in
theorem substOldPostSubset:
  (Imperative.HasVarsPure.getVars (P:=Expression)
    (substOld h2 (Lambda.LExpr.fvar m h1 ty) post)).Subset
    (Imperative.HasVarsPure.getVars (P:=Expression) post ++ [h1]) := by
  change (Lambda.LExpr.LExpr.getVars (substOld h2 (Lambda.LExpr.fvar m h1 ty) post)).Subset (Lambda.LExpr.LExpr.getVars post ++ [h1])
  induction post <;> simp only [substOld, Lambda.LExpr.LExpr.getVars] at *
  case app =>
    split
    · split <;> simp_all [Lambda.LExpr.LExpr.getVars, List.Subset]
    · simp [Lambda.LExpr.LExpr.getVars, List.Subset] at * <;> grind only
  all_goals simp [List.Subset] at * <;> grind only
