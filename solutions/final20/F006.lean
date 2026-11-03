theorem liftBVars_denote
    {e : LExpr T.mono} {τ : LMonoTy}
    {Δ₁ Δ_insert Δ_outer : List LMonoTy}
    (h_orig : LExpr.HasTypeA (Δ₁ ++ Δ_outer) e τ)
    (h_lifted : LExpr.HasTypeA (Δ₁ ++ (Δ_insert ++ Δ_outer)) (LExpr.liftBVars Δ_insert.length e Δ₁.length) τ)
    (bv₁ : BVarVal tcInterp vt Δ₁)
    (bv_insert : BVarVal tcInterp vt Δ_insert)
    (bv_outer : BVarVal tcInterp vt Δ_outer)
    : LExpr.denote tcInterp opInterp fvarVal vt (HList.append bv₁ (HList.append bv_insert bv_outer))
        (LExpr.liftBVars Δ_insert.length e Δ₁.length) τ h_lifted =
      LExpr.denote tcInterp opInterp fvarVal vt (HList.append bv₁ bv_outer) e τ h_orig := by
  have unlift {a : LExpr T.mono} {σ : LMonoTy} {Δ : List LMonoTy}
      (h : LExpr.HasTypeA (Δ ++ (Δ_insert ++ Δ_outer))
        (LExpr.liftBVars Δ_insert.length a Δ.length) σ) :
      LExpr.HasTypeA (Δ ++ Δ_outer) a σ := by
    apply LExpr.typeCheck_to_HasTypeA
    have ht := LExpr.HasTypeA_to_typeCheck h
    rw [← List.append_assoc, liftBVars_typeCheck] at ht
    exact ht
  induction e generalizing Δ₁ bv₁ τ <;> dsimp only [LExpr.liftBVars] at h_lifted ⊢
  case const m c => rfl
  case op m o ty => cases ty <;> rfl
  case fvar m name ty => cases ty <;> rfl
  case bvar m i =>
    have ho := HasTypeA.bvar_inv h_orig
    by_cases h_ge : i ≥ Δ₁.length
    · simp only [if_pos h_ge] at h_lifted ⊢
      rw [denote_bvar _ _ _ _ _ h_lifted, denote_bvar _ _ _ _ _ h_orig]
      rw [List.getElem?_append_right h_ge] at ho
      have hi : i + Δ_insert.length - Δ₁.length - Δ_insert.length = i - Δ₁.length := by omega
      have hm : (Δ_insert ++ Δ_outer)[i + Δ_insert.length - Δ₁.length]? = some τ := by
        rw [List.getElem?_append_right (by omega), hi]
        exact ho
      rw [HList.get_append_right bv₁ (bv_insert.append bv_outer) _ (HasTypeA.bvar_inv h_lifted) hm (by omega),
          HList.get_append_right bv_insert bv_outer _ hm (by simpa only [hi] using ho) (by omega),
          HList.get_append_right bv₁ bv_outer i (HasTypeA.bvar_inv h_orig) ho h_ge]
      simp only [hi]
    · simp only [if_neg h_ge] at h_lifted ⊢
      rw [denote_bvar _ _ _ _ _ h_lifted, denote_bvar _ _ _ _ _ h_orig]
      rw [List.getElem?_append_left (by omega)] at ho
      rw [HList.get_append_left bv₁ _ i (HasTypeA.bvar_inv h_lifted) ho,
          HList.get_append_left bv₁ _ i (HasTypeA.bvar_inv h_orig) ho]
  case app m fn arg ih_fn ih_arg =>
    obtain ⟨aty_l, h_fn_l, h_arg_l⟩ := HasTypeA.app_inv h_lifted
    have h_fn_o := unlift h_fn_l
    have h_arg_o := unlift h_arg_l
    rw [denote_app _ h_fn_l h_arg_l h_lifted, denote_app _ h_fn_o h_arg_o h_orig,
        ih_fn h_fn_o h_fn_l bv₁, ih_arg h_arg_o h_arg_l bv₁]
  case abs m name ty body ih =>
    cases ty with
    | none => rfl
    | some aty =>
      obtain ⟨rty_l, h_eq_l, h_body_l⟩ := HasTypeA.abs_inv h_lifted
      subst h_eq_l
      have h_body_o := unlift (Δ := aty :: Δ₁) h_body_l
      rw [denote_abs _ h_body_l h_lifted, denote_abs _ h_body_o h_orig]
      funext x
      exact ih h_body_o h_body_l (.cons x bv₁)
  case ite m c t e ih_c ih_t ih_e =>
    obtain ⟨h_c_l, h_t_l, h_e_l⟩ := HasTypeA.ite_inv h_lifted
    have h_c_o := unlift h_c_l
    have h_t_o := unlift h_t_l
    have h_e_o := unlift h_e_l
    rw [denote_ite _ h_c_l h_t_l h_e_l h_lifted,
        denote_ite _ h_c_o h_t_o h_e_o h_orig,
        ih_c h_c_o h_c_l bv₁, ih_t h_t_o h_t_l bv₁, ih_e h_e_o h_e_l bv₁]
  case eq m e1 e2 ih1 ih2 =>
    generalize hl : HasTypeA.eq_inv h_lifted = dl
    generalize ho : HasTypeA.eq_inv h_orig = dorig
    rcases dl with ⟨ty_l, h_τ_l, h_1_l, h_2_l⟩
    rcases dorig with ⟨ty_o, h_τ_o, h_1_o, h_2_o⟩
    subst h_τ_o
    have h_ty := HasTypeA_unique (unlift h_1_l) h_1_o
    subst h_ty
    simp only [LExpr.denote, hl, ho]
    rw [ih1 h_1_o h_1_l bv₁, ih2 h_2_o h_2_l bv₁]
  case quant m qk name qty tr body ih_tr ih_body =>
    cases qty with
    | none => rfl
    | some qty' =>
      obtain ⟨_, h_τ_l, h_tr_l, h_body_l⟩ := HasTypeA.quant_inv h_lifted
      subst h_τ_l
      have h_body_o := unlift (Δ := qty' :: Δ₁) h_body_l
      exact denote_quant_congr h_body_l h_body_o h_lifted h_orig
        (fun x => ih_body h_body_o h_body_l (.cons x bv₁))
