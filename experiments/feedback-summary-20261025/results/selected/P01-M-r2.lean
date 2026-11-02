open OldExpressions in
theorem substOldPostSubset:
  (Imperative.HasVarsPure.getVars (P:=Expression)
    (substOld h2 (Lambda.LExpr.fvar m h1 ty) post)).Subset
    (Imperative.HasVarsPure.getVars (P:=Expression) post ++ [h1]) := by
  simp only [Imperative.HasVarsPure.getVars]
  intro x
  induction post <;> dsimp only [substOld]
  case' app => split <;> (try split)
  all_goals simp only [Lambda.LExpr.LExpr.getVars, List.mem_append, List.mem_singleton, List.not_mem_nil] at * <;> grind only
