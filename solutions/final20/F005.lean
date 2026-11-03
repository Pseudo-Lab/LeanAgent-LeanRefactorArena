theorem liftBVars_typeCheck
    (e : LExpr T.mono)
    {Δ₁ Δ_insert Δ_outer : List LMonoTy}
    : LExpr.typeCheck (Δ₁ ++ Δ_insert ++ Δ_outer) (LExpr.liftBVars Δ_insert.length e Δ₁.length)
      = LExpr.typeCheck (Δ₁ ++ Δ_outer) e := by
  induction e generalizing Δ₁
  all_goals try cases ‹Option LMonoTy›
  all_goals dsimp only [LExpr.liftBVars, LExpr.typeCheck]
  case bvar =>
    split <;>
      simp (disch := omega) only [LExpr.typeCheck, List.append_assoc,
        List.getElem?_append_left, List.getElem?_append_right,
        Nat.sub_sub, Nat.add_sub_add_right]
  all_goals
    try simp only [← List.cons_append, ← List.length_cons (a := ‹LMonoTy›)]
    simp_all only
