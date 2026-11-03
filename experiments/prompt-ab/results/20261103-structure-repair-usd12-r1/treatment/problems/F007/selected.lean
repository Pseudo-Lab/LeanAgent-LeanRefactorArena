theorem LExpr.typeCheck_to_HasTypeA {T : LExprParams} {Δ : List LMonoTy}
    {e : LExpr T.mono} {τ : LMonoTy}
    (h : typeCheck Δ e = some τ) : HasTypeA Δ e τ := by
  induction e generalizing Δ τ
  case const => cases h; exact .const
  case op _ _ ty | fvar _ _ ty => cases ty <;> cases h <;> constructor
  case bvar => exact .bvar h
  case' abs _ _ ty _ _ | quant _ _ _ ty _ _ _ _ =>
    cases ty <;> try cases h
  all_goals simp only [typeCheck, bind, Option.bind_eq_some_iff, guard,
    beq_iff_eq, pure, failure, Option.ite_some_none_eq_some,
    Option.some.injEq, and_true, exists_const] at h
  all_goals repeat (rcases h with ⟨_, h⟩)
  case' app =>
    have ha := LMonoTy.isArrow_some (by assumption)
    cases ha
  all_goals
    subst_vars
    constructor <;> solve_by_elim only [*]
