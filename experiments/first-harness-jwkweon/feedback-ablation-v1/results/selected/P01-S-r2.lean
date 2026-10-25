open OldExpressions in
theorem substOldPostSubset:
  (Imperative.HasVarsPure.getVars (P:=Expression)
    (substOld h2 (Lambda.LExpr.fvar m h1 ty) post)).Subset
    (Imperative.HasVarsPure.getVars (P:=Expression) post ++ [h1]) := by
  simp only [Imperative.HasVarsPure.getVars]
  induction post <;> simp only [substOld]
  all_goals (repeat' split)
  all_goals simp only [Lambda.LExpr.LExpr.getVars, List.Subset, List.mem_append, List.mem_singleton] at *
  all_goals grind only
