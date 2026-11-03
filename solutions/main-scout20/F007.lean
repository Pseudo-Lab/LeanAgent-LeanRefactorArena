theorem LExpr.typeCheck_to_HasTypeA {T : LExprParams} {Δ : List LMonoTy}
    {e : LExpr T.mono} {τ : LMonoTy}
    (h : typeCheck Δ e = some τ) : HasTypeA Δ e τ := by
  induction e generalizing Δ τ
  all_goals try cases ‹Option LMonoTy›
  all_goals simp only [typeCheck, bind, Option.bind_eq_some_iff, guard, pure, failure, beq_iff_eq, Option.ite_none_right_eq_some, Option.some.injEq, reduceCtorEq, and_true] at h
  case const | op.some | fvar.some => cases h; constructor
  case bvar => exact .bvar h
  case' abs.some => rcases h with ⟨_, hb, rfl⟩
  case' quant.some => rcases h with ⟨_, ht, _, hb, _, rfl, rfl⟩
  case' app =>
    rcases h with ⟨_, hf, _, ha, ⟨_, _⟩, hp, _, rfl, rfl⟩
    obtain rfl := LMonoTy.isArrow_some hp
  case' ite => rcases h with ⟨_, hc, _, ht, _, he, _, rfl, _, rfl, rfl⟩
  case' eq => rcases h with ⟨_, ha, _, hb, _, rfl, rfl⟩
  all_goals constructor <;> (apply_assumption <;> assumption)
