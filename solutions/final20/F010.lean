theorem denote_ext
    {e : LExpr T.mono} {τ : LMonoTy}
    {Δ : List LMonoTy}
    {opInterp₁ opInterp₂ : OpInterp tcInterp}
    {fvarVal₁ fvarVal₂ : FreeVarVal T tcInterp}
    {bvarVal₁ bvarVal₂ : BVarVal tcInterp vt Δ}
    (h_op : ∀ o ty, (o, some ty) ∈ e.usedOps → opInterp₁ o.name (LMonoTy.substTyVars vt ty) = opInterp₂ o.name (LMonoTy.substTyVars vt ty))
    (h_fvar : ∀ name ty, (name, some ty) ∈ e.freeVars → fvarVal₁ name (LMonoTy.substTyVars vt ty) = fvarVal₂ name (LMonoTy.substTyVars vt ty))
    (h_bvar : ∀ i (τ' : LMonoTy) (h₁ : Δ[i]? = some τ') (h₂ : Δ[i]? = some τ'), i ∈ e.usedBvars → bvarVal₁.get i h₁ = bvarVal₂.get i h₂)
    (h₁ : LExpr.HasTypeA Δ e τ)
    (h₂ : LExpr.HasTypeA Δ e τ)
    : LExpr.denote tcInterp opInterp₁ fvarVal₁ vt bvarVal₁ e τ h₁ =
      LExpr.denote tcInterp opInterp₂ fvarVal₂ vt bvarVal₂ e τ h₂ := by
  induction h₁
  case const => rfl
  case op => exact h_op _ _ (List.Mem.head _)
  case fvar => exact h_fvar _ _ (List.Mem.head _)
  case bvar hi => exact h_bvar _ _ hi hi (List.Mem.head _)
  case abs hb ih =>
    exact (denote_abs bvarVal₁ hb _).trans
      ((funext fun x => ih h_op h_fvar (bvar_ext_cons tcInterp vt x h_bvar) hb).trans
        (denote_abs bvarVal₂ hb h₂).symm)
  case quant ht hb ih_tr ih =>
    exact denote_quant_congr hb hb _ h₂ fun x =>
      ih (fun o ty ho => h_op o ty (List.mem_append_right _ ho))
        (fun n ty hf => h_fvar n ty (List.mem_append_right _ hf))
        (bvar_ext_cons tcInterp vt x (fun i ty hi₁ hi₂ hm => h_bvar i ty hi₁ hi₂ (List.mem_append_right _ hm))) hb
  all_goals
    dsimp only [LExpr.usedOps, LExpr.freeVars, LExpr.usedBvars] at h_op h_fvar h_bvar
    simp only [List.mem_append, or_imp, forall_and] at h_op h_fvar h_bvar
  case app hf ha ih_fn ih_arg =>
    exact (denote_app bvarVal₁ hf ha _).trans
      ((congr (ih_fn h_op.1 h_fvar.1 h_bvar.1 hf)
        (ih_arg h_op.2 h_fvar.2 h_bvar.2 ha)).trans (denote_app bvarVal₂ hf ha h₂).symm)
  case ite hc ht he ih_c ih_t ih_e =>
    exact (denote_ite bvarVal₁ hc ht he _).trans
      ((congr (congr (congrArg (fun c t e => bif c then t else e)
        (ih_c h_op.1.1 h_fvar.1.1 h_bvar.1.1 hc))
        (ih_t h_op.1.2 h_fvar.1.2 h_bvar.1.2 ht))
        (ih_e h_op.2 h_fvar.2 h_bvar.2 he)).trans (denote_ite bvarVal₂ hc ht he h₂).symm)
  case eq Δ e1 ty e2 m ha hc ih1 ih2 =>
    have hleft := ih1 h_op.1 h_fvar.1 h_bvar.1 ha
    have hright := ih2 h_op.2 h_fvar.2 h_bvar.2 hc
    by_cases heq : LExpr.denote tcInterp opInterp₁ fvarVal₁ vt bvarVal₁ e1 ty ha = LExpr.denote tcInterp opInterp₁ fvarVal₁ vt bvarVal₁ e2 ty hc
    · exact (denote_eq_true bvarVal₁ ha hc _ heq).trans
        (denote_eq_true bvarVal₂ ha hc h₂ (hleft.symm.trans (heq.trans hright))).symm
    · exact (denote_eq_false bvarVal₁ ha hc _ heq).trans
        (denote_eq_false bvarVal₂ ha hc h₂ (fun h => heq (hleft.trans (h.trans hright.symm)))).symm
