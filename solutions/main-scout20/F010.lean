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
  change _ = LExpr.denote tcInterp opInterp₂ fvarVal₂ vt bvarVal₂ e τ h₁
  clear h₂
  revert h_op h_fvar h_bvar
  induction h₁ <;> intro ho hf hb
  case const => rfl
  case op => exact ho _ _ (List.Mem.head _)
  case fvar => exact hf _ _ (List.Mem.head _)
  case bvar hi => exact hb _ _ hi hi (List.Mem.head _)
  case abs ht ih =>
    rw [denote_abs _ ht, denote_abs _ ht]
    funext x
    exact ih ho hf (bvar_ext_cons tcInterp vt x hb)
  case quant ht hu iht ihu =>
    apply denote_quant_congr hu hu
    intro x
    exact ihu (fun o ty h => ho o ty (List.mem_append_right _ h))
      (fun n ty h => hf n ty (List.mem_append_right _ h))
      (bvar_ext_cons tcInterp vt x (fun i ty h₁ h₂ h => hb i ty h₁ h₂ (List.mem_append_right _ h)))
  all_goals simp (config := { dsimp := false }) only [LExpr.usedOps, LExpr.freeVars, LExpr.usedBvars, List.mem_append, or_imp, forall_and] at ho hf hb
  case app ht hu iht ihu =>
    rw [denote_app _ ht hu, denote_app _ ht hu,
      iht ho.1 hf.1 hb.1, ihu ho.2 hf.2 hb.2]
  case ite hc ht hu ihc iht ihu =>
    rw [denote_ite _ hc ht hu, denote_ite _ hc ht hu,
      ihc ho.1.1 hf.1.1 hb.1.1, iht ho.1.2 hf.1.2 hb.1.2, ihu ho.2 hf.2 hb.2]
  case eq ht hu iht ihu =>
    have hleft := iht ho.1 hf.1 hb.1
    have hright := ihu ho.2 hf.2 hb.2
    by_cases h : LExpr.denote tcInterp opInterp₁ fvarVal₁ vt bvarVal₁ _ _ ht = LExpr.denote tcInterp opInterp₁ fvarVal₁ vt bvarVal₁ _ _ hu
    · exact (denote_eq_true _ ht hu _ h).trans
        (denote_eq_true _ ht hu _ (hleft.symm.trans (h.trans hright))).symm
    · exact (denote_eq_false _ ht hu _ h).trans
        (denote_eq_false _ ht hu _ (fun hh => h (hleft.trans (hh.trans hright.symm)))).symm
