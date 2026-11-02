open OldExpressions in
theorem extractedOldExprInVars :
  NormalizedOldExpr post →
  (extractOldExprVars post).Subset
  (Imperative.HasVarsPure.getVars post) := by
  have ha {a b c d : List Expression.Ident} (h : a.Subset c) (k : b.Subset d) :
      (a ++ b).Subset (c ++ d) :=
    fun _ hx => List.mem_append.mpr (Or.imp (h ·) (k ·) (List.mem_append.mp hx))
  intro h
  induction h
  case const | op | bvar | fvar => exact List.nil_subset _
  case abs ih => exact ih
  case quant ih₁ ih₂ | eq ih₁ ih₂ => exact ha ih₁ ih₂
  case ite ih₁ ih₂ ih₃ => exact ha (ha ih₁ ih₂) ih₃
  case app fn e hfn he hn ih₁ ih₂ =>
    unfold extractOldExprVars
    split
    · exact fun _ h => h
    · next hf =>
        cases hn .oldPred
        exfalso
        apply hf
        rfl
    · exact ha ih₁ ih₂
