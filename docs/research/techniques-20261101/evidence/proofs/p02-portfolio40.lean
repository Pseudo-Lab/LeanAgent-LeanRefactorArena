open OldExpressions in
theorem extractedOldExprInVars :
  NormalizedOldExpr post →
  (extractOldExprVars post).Subset
  (Imperative.HasVarsPure.getVars post) := by
  rintro -
  apply List.Sublist.subset
  fun_induction extractOldExprVars post <;>
    repeat first
      | assumption
      | apply List.nil_sublist
      | apply List.Sublist.append
      | apply List.Sublist.cons₂
