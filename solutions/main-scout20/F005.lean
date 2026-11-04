theorem liftBVars_typeCheck
    (e : LExpr T.mono)
    {Δ₁ Δ_insert Δ_outer : List LMonoTy}
    : LExpr.typeCheck (Δ₁ ++ Δ_insert ++ Δ_outer) (LExpr.liftBVars Δ_insert.length e Δ₁.length)
      = LExpr.typeCheck (Δ₁ ++ Δ_outer) e := by
  induction e generalizing Δ₁ <;> try cases ‹Option LMonoTy›
  all_goals simp_all only [LExpr.liftBVars, LExpr.typeCheck]
  all_goals try simp_all only [← List.cons_append, ← List.length_cons (a := ‹LMonoTy›)]
  all_goals split <;> simp only [LExpr.typeCheck] <;> grind
