lemma Typing.preservation (der : Typing Γ t τ) (step : t ⭢βᵛ t') : Typing Γ t' τ := by
  induction der generalizing t'
  case' app σ τ _ der _ ih₁ ih₂ =>
    cases step
    case' abs =>
      have ⟨_, _, _, _⟩ := der.abs_inv
        (by grind [Sub.refl] : Sub _ _ $ σ.arrow τ)
  case' tapp Γ _ σ τ σ' der _ ih =>
    cases step
    case tabs =>
      clear ih
      have ⟨_, _, _, _⟩ := der.tabs_inv
        (by grind [Sub.refl] : Sub Γ _ $ σ.all τ)
      have ⟨X, mem⟩ := fresh_exists $ free_union [Ty.fv, fvTy] Var
      simp at mem
      have : Γ = Context.mapVal (·[X := σ']) [] ++ Γ := rfl
      rw [openTy_substTy_intro (X := X), open_subst_intro (X := X)] <;> grind [subst_ty]
  case' let' L _ _ ih₁ ih₂ =>
    cases step
    case let_bind red₁ _ => apply Typing.let' L $ ih₁ red₁; assumption
  case' case Γ _ σ τ _ _ _ L der _ _ ih₁ ih₂ ih₃ =>
    clear ih₃
    have sub : Sub Γ (σ.sum τ) $ σ.sum τ := by grind [Sub.refl]
    have := List.nil_append Γ
    cases step
    case «case» red₁ _ _ => apply Typing.case L $ ih₁ red₁ <;> assumption
    case' case_inl =>
      have ⟨_, _⟩ := der.inl_inv sub
    case' case_inr =>
      have ⟨_, _⟩ := der.inr_inv sub
  case' app.abs | let' | case.case_inl | case.case_inr =>
    clear ih₁ ih₂
    have ⟨x, hx⟩ := fresh_exists $ free_union [fvTm] Var
    simp at hx
    try
      case app.abs =>
        grind [openTm_substTm_intro (x := x), subst_tm, Sub.weaken]
    all_goals grind [openTm_substTm_intro (x := x), subst_tm]
  all_goals grind [cases Red]
