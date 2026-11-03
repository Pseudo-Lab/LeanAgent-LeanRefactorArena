open OldExpressions in
theorem substOldPostSubset:
  (Imperative.HasVarsPure.getVars (P:=Expression)
    (substOld h2 (Lambda.LExpr.fvar m h1 ty) post)).Subset
    (Imperative.HasVarsPure.getVars (P:=Expression) post ++ [h1]) := by
  induction post <;> simp only [substOld]
  all_goals (repeat split) <;> simp only [Imperative.HasVarsPure.getVars, Lambda.LExpr.LExpr.getVars, List.Subset, List.mem_append, List.mem_singleton, List.not_mem_nil] at *
  all_goals intro x hx; grind only
