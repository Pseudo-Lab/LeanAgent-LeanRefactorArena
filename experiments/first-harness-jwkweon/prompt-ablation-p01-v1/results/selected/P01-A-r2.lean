open OldExpressions in
theorem substOldPostSubset:
  (Imperative.HasVarsPure.getVars (P:=Expression)
    (substOld h2 (Lambda.LExpr.fvar m h1 ty) post)).Subset
    (Imperative.HasVarsPure.getVars (P:=Expression) post ++ [h1]) := by
  simp only [Imperative.HasVarsPure.getVars]
  intro x hx
  induction post <;> simp only [substOld] at hx
  all_goals
    repeat' split at hx
    all_goals
      simp only [Lambda.LExpr.LExpr.getVars, List.mem_append, List.mem_cons,
        List.not_mem_nil, or_false] at * <;> grind only
