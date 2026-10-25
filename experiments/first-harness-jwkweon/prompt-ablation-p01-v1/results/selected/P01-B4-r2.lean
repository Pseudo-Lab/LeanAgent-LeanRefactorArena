open OldExpressions in
theorem substOldPostSubset:
  (Imperative.HasVarsPure.getVars (P:=Expression)
    (substOld h2 (Lambda.LExpr.fvar m h1 ty) post)).Subset
    (Imperative.HasVarsPure.getVars (P:=Expression) post ++ [h1]) := by
  induction post <;> simp [substOld]
  all_goals try assumption
  all_goals try (split <;> try split)
  all_goals dsimp [Imperative.HasVarsPure.getVars, Lambda.LExpr.LExpr.getVars] at *
  all_goals try apply List.Subset.app
  all_goals try apply List.Subset.app
  all_goals first
    | (apply List.Subset.trans (by assumption)
       intro x hx
       simp only [List.mem_append, List.mem_singleton] at hx ⊢
       rcases hx with hx | hx <;> simp [hx])
    | (intro x hx; simp_all)
