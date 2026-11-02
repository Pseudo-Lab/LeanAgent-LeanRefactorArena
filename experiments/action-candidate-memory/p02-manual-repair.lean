open OldExpressions in
theorem extractedOldExprInVars :
  NormalizedOldExpr post →
  (extractOldExprVars post).Subset
  (Imperative.HasVarsPure.getVars post) := by
  intro h
  induction h with
  | app hfn he hn ihfn ihe =>
    simp only [Imperative.HasVarsPure.getVars, Lambda.LExpr.LExpr.getVars]
    unfold extractOldExprVars
    split
    · simp only [Lambda.LExpr.LExpr.getVars, List.nil_append]
      exact fun _ hx => hx
    · next hfalse =>
      exfalso
      have hf := hn (by constructor)
      cases hf
      apply hfalse
      rfl
    · intro x hx
      simp only [List.mem_append] at hx ⊢
      exact hx.elim (fun h => Or.inl (ihfn h)) (fun h => Or.inr (ihe h))
  | _ =>
    simp_all [Imperative.HasVarsPure.getVars, extractOldExprVars,
      Lambda.LExpr.LExpr.getVars, List.Subset, List.mem_append] <;>
      (intro x hx
       cases hx <;> try simp_all
       all_goals
         rename_i hx
         cases hx <;> simp_all)
