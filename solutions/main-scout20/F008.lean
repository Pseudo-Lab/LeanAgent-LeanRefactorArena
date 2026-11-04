theorem callOfLFunc_constr_disjoint_denote
    {T : LExprParams} [DecidableEq T.IDMeta] [Inhabited T.mono.base.IDMeta]
    (tcInterp : TyConstrInterp) (opInterp : OpInterp tcInterp)
    (fvarVal : FreeVarVal T tcInterp) (vt : TyVarVal)
    {F : @Factory T} {tf : @TypeFactory T.IDMeta}
    {e₁ e₂ : LExpr T.mono} {τ : LMonoTy}
    {callee₁ callee₂ : LExpr T.mono}
    {args₁ args₂ : List (LExpr T.mono)}
    {f₁ f₂ : LFunc T.mono.base}
    (h₁ : LExpr.HasTypeA [] e₁ τ)
    (h₂ : LExpr.HasTypeA [] e₂ τ)
    (hcall₁ : Factory.callOfLFunc F e₁ = some (callee₁, args₁, f₁))
    (hcall₂ : Factory.callOfLFunc F e₂ = some (callee₂, args₂, f₂))
    (hconstr₁ : f₁.isConstr = true) (hconstr₂ : f₂.isConstr = true)
    (hdiffname : f₁.name.name ≠ f₂.name.name)
    (hoc₁ : OpsConsistent F e₁) (hoc₂ : OpsConsistent F e₂)
    (hfwf : FactoryWF F) (hcwf : Factory.ConstrWellFormed F tf)
    (htfwf : TypeFactoryWF tf)
    (hConstrIC : ConstrInterpConsistent tcInterp opInterp F)
    : LExpr.denote tcInterp opInterp fvarVal vt .nil e₁ τ h₁ ≠
      LExpr.denote tcInterp opInterp fvarVal vt .nil e₂ τ h₂ := by
  obtain ⟨argTys₁, _, m₁, name₁, h_args₁, rfl, hcallee₁, hdenote₁⟩ :=
    callOfLFunc_denote tcInterp opInterp fvarVal vt hcall₁ h₁
  obtain ⟨argTys₂, _, m₂, name₂, h_args₂, rfl, hcallee₂, hdenote₂⟩ :=
    callOfLFunc_denote tcInterp opInterp fvarVal vt hcall₂ h₂
  obtain ⟨_, _, _, hcallee₁', hget₁⟩ := Factory.callOfLFunc_getElem? hcall₁
  obtain ⟨_, _, _, hcallee₂', hget₂⟩ := Factory.callOfLFunc_getElem? hcall₂
  rw [hcallee₁] at hcallee₁'; cases hcallee₁'
  rw [hcallee₂] at hcallee₂'; cases hcallee₂'
  rw [hdenote₁, hdenote₂, ← Factory.getElem?_name hget₁, ← Factory.getElem?_name hget₂]
  obtain ⟨tySubst₁, _, htySubst₁⟩ := OpsConsistent_callOfLFunc hoc₁ hcall₁
  have hty_op_subst₁ := htySubst₁ m₁ name₁ _ hcallee₁
  rw [subst_mkArrow'] at hty_op_subst₁
  have ⟨hτ_eq₁, hargTys_eq₁⟩ := LMonoTy.mkArrow'_injective (h := hty_op_subst₁) (by
    simpa only [List.length_map] using h_args₁.length_eq.symm.trans (Factory.callOfLFunc_arity hcall₁))
  let vt'₁ : TyVarVal := fun x => match tySubst₁.find? x with
    | some t => LMonoTy.substTyVars vt t | none => vt x
  obtain ⟨tySubst₂, _, htySubst₂⟩ := OpsConsistent_callOfLFunc hoc₂ hcall₂
  have hty_op_subst₂ := htySubst₂ m₂ name₂ _ hcallee₂
  rw [subst_mkArrow'] at hty_op_subst₂
  have ⟨hτ_eq₂, hargTys_eq₂⟩ := LMonoTy.mkArrow'_injective (h := hty_op_subst₂) (by
    simpa only [List.length_map] using h_args₂.length_eq.symm.trans (Factory.callOfLFunc_arity hcall₂))
  have hmem₁ := callOfLFunc_func_mem _ _ _ _ _ false hcall₁
  have hmem₂ := callOfLFunc_func_mem _ _ _ _ _ false hcall₂
  obtain ⟨d₁, hd₁_mem, c₁, _, hf₁_eq⟩ := hcwf f₁ hmem₁ hconstr₁
  obtain ⟨d₂, hd₂_mem, c₂, _, hf₂_eq⟩ := hcwf f₂ hmem₂ hconstr₂
  have ho₁ : f₁.output = dataDefault d₁ := by subst hf₁_eq; rfl
  have ho₂ : f₂.output = dataDefault d₂ := by subst hf₂_eq; rfl
  cases htfwf.eq_of_name_eq hd₁_mem hd₂_mem (by
    have h := hτ_eq₁.symm.trans hτ_eq₂
    rw [ho₁, ho₂] at h
    unfold dataDefault data at h
    rw [LMonoTy.subst_tcons, LMonoTy.subst_tcons] at h
    exact (LMonoTy.tcons.inj h).1)
  have h_same_output := ho₁.trans ho₂.symm
  have h_subst_inputs_eq := constr_same_output_implies_same_argTys
    (S₁ := tySubst₁) (S₂ := tySubst₂)
    (hfwf.lfuncs_wf f₂ hmem₂)
    (by rw [← h_same_output, ← hτ_eq₁, h_same_output, ← hτ_eq₂])
    (constrFunc_output_covers_typeArgs hcwf hmem₂ hconstr₂)
  have hdisj := hConstrIC.constr_disjoint f₁ f₂ hmem₁ hmem₂ hconstr₁ hconstr₂ hdiffname vt'₁
  dsimp only at hdisj
  rw [← h_same_output] at hdisj
  unfold TyVarVal at vt vt'₁
  have hvt : LMonoTy.substTyVars vt'₁ = LMonoTy.substTyVars vt ∘ LMonoTy.subst tySubst₁ :=
    funext fun ty => (substTyVars_subst vt tySubst₁ ty).symm
  rw [hvt, ListMap.values_eq_map_snd, ListMap.values_eq_map_snd,
    ← List.map_map, ← List.map_map, ← hargTys_eq₁, h_subst_inputs_eq,
    ← hargTys_eq₂, Function.comp_apply, ← hτ_eq₁] at hdisj
  have hop (n : String) {s t : LSort} (h : s = t) :
      (h ▸ opInterp n s) = opInterp n t := by cases h; rfl
  simpa only [hop] using
    hdisj rfl (denoteArgs tcInterp opInterp fvarVal vt .nil args₁ argTys₁ h_args₁)
      (denoteArgs tcInterp opInterp fvarVal vt .nil args₂ argTys₂ h_args₂)
