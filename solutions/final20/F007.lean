theorem LExpr.typeCheck_to_HasTypeA {T : LExprParams} {Δ : List LMonoTy}
    {e : LExpr T.mono} {τ : LMonoTy}
    (h : typeCheck Δ e = some τ) : HasTypeA Δ e τ := by
  induction e generalizing Δ τ
  case const => cases h; exact .const
  case op _ _ ty | fvar _ _ ty => cases ty <;> cases h <;> constructor
  case bvar => exact .bvar h
  case' abs _ _ ty body ih | quant _ _ _ ty tr body ihtr ihbody =>
    cases ty <;> try cases h
  all_goals simp only [typeCheck, bind, Option.bind_eq_some_iff, guard,
    beq_iff_eq, pure, failure, Option.ite_some_none_eq_some,
    Option.some.injEq, and_true, exists_const] at h
  case' abs => rcases h with ⟨rty, hrty, rfl⟩
  case' quant => rcases h with ⟨t, ht, _, hb, rfl, rfl⟩
  case' app =>
    rcases h with ⟨fty, hf, aty, ha, ⟨dom, cod⟩, hp, rfl, rfl⟩
    cases LMonoTy.isArrow_some hp
  case' ite => rcases h with ⟨_, hc, tty, ht, _, he, rfl, rfl, rfl⟩
  case' eq => rcases h with ⟨ty1, h1, _, h2, rfl, rfl⟩
  all_goals constructor <;> solve_by_elim only [*]
