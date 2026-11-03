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
  obtain ⟨argTys₁, ty_op₁, m₁, name₁, h_args₁, hty_op₁, hcallee₁, hdenote₁⟩ :=
    callOfLFunc_denote tcInterp opInterp fvarVal vt hcall₁ h₁
  obtain ⟨argTys₂, ty_op₂, m₂, name₂, h_args₂, hty_op₂, hcallee₂, hdenote₂⟩ :=
    callOfLFunc_denote tcInterp opInterp fvarVal vt hcall₂ h₂
  subst hty_op₁; subst hty_op₂
  obtain ⟨_, fname₁, _, hcallee₁', hget₁⟩ := Factory.callOfLFunc_getElem? hcall₁
  obtain ⟨_, fname₂, _, hcallee₂', hget₂⟩ := Factory.callOfLFunc_getElem? hcall₂
  rw [hcallee₁] at hcallee₁'; cases hcallee₁'
  rw [hcallee₂] at hcallee₂'; cases hcallee₂'
  have hname₁ := Factory.getElem?_name hget₁
  have hname₂ := Factory.getElem?_name hget₂
  rw [hdenote₁, hdenote₂, ← hname₁, ← hname₂]
  obtain ⟨tySubst₁, _, htySubst₁⟩ := OpsConsistent_callOfLFunc hoc₁ hcall₁
  have hty_op_subst₁ := htySubst₁ m₁ name₁ (LMonoTy.mkArrow' τ argTys₁) hcallee₁
  rw [subst_mkArrow'] at hty_op_subst₁
  have hlen₁ : argTys₁.length = ((f₁.inputs.map Prod.snd).map (LMonoTy.subst tySubst₁)).length := by
    simp only [List.length_map]
    exact h_args₁.length_eq.symm.trans (Factory.callOfLFunc_arity hcall₁)
  obtain ⟨hτ_eq₁, hargTys_eq₁⟩ := LMonoTy.mkArrow'_injective hlen₁ hty_op_subst₁
  let vt'₁ : TyVarVal := fun x => match tySubst₁.find? x with
    | some t => LMonoTy.substTyVars vt t | none => vt x
  have h_outputSort_eq₁ : LMonoTy.substTyVars vt τ = LMonoTy.substTyVars vt'₁ f₁.output := by
    rw [hτ_eq₁]; exact substTyVars_subst vt tySubst₁ f₁.output
  have h_inputSorts_eq₁ : argTys₁.map (LMonoTy.substTyVars vt) =
      (f₁.inputs.map Prod.snd).map (LMonoTy.substTyVars vt'₁) := by
    rw [hargTys_eq₁]; simp only [List.map_map]
    congr 1; funext ⟨_, ty⟩
    exact substTyVars_subst vt tySubst₁ ty
  obtain ⟨tySubst₂, _, htySubst₂⟩ := OpsConsistent_callOfLFunc hoc₂ hcall₂
  have hty_op_subst₂ := htySubst₂ m₂ name₂ (LMonoTy.mkArrow' τ argTys₂) hcallee₂
  rw [subst_mkArrow'] at hty_op_subst₂
  have hlen₂ : argTys₂.length = ((f₂.inputs.map Prod.snd).map (LMonoTy.subst tySubst₂)).length := by
    simp only [List.length_map]
    exact h_args₂.length_eq.symm.trans (Factory.callOfLFunc_arity hcall₂)
  obtain ⟨hτ_eq₂, hargTys_eq₂⟩ := LMonoTy.mkArrow'_injective hlen₂ hty_op_subst₂
  have hmem₁ := callOfLFunc_func_mem _ _ _ _ _ false hcall₁
  have hmem₂ := callOfLFunc_func_mem _ _ _ _ _ false hcall₂
  obtain ⟨d₁, hd₁_mem, c₁, _, hf₁_eq⟩ := hcwf f₁ hmem₁ hconstr₁
  obtain ⟨d₂, hd₂_mem, c₂, _, hf₂_eq⟩ := hcwf f₂ hmem₂ hconstr₂
  have ho₁ : f₁.output = dataDefault d₁ := by subst hf₁_eq; rfl
  have ho₂ : f₂.output = dataDefault d₂ := by subst hf₂_eq; rfl
  have hτ_tcons₁ : τ = .tcons d₁.name (LMonoTys.subst tySubst₁ (d₁.typeArgs.map .ftvar)) := by
    rw [hτ_eq₁, ho₁]; unfold dataDefault data; rw [LMonoTy.subst_tcons]
  have hτ_tcons₂ : τ = .tcons d₂.name (LMonoTys.subst tySubst₂ (d₂.typeArgs.map .ftvar)) := by
    rw [hτ_eq₂, ho₂]; unfold dataDefault data; rw [LMonoTy.subst_tcons]
  have hd_name := (LMonoTy.tcons.inj (hτ_tcons₁.symm.trans hτ_tcons₂)).1
  have hd_eq := htfwf.eq_of_name_eq hd₁_mem hd₂_mem hd_name
  subst hd_eq
  have h_same_output : f₁.output = f₂.output := by rw [ho₁, ho₂]
  have h_subst_output_eq : LMonoTy.subst tySubst₁ f₂.output = LMonoTy.subst tySubst₂ f₂.output := by
    rw [← h_same_output, ← hτ_eq₁, h_same_output, ← hτ_eq₂]
  have h_subst_inputs_eq := constr_same_output_implies_same_argTys
    (hfwf.lfuncs_wf f₂ hmem₂) h_subst_output_eq
    (constrFunc_output_covers_typeArgs hcwf hmem₂ hconstr₂)
  have hdisj := hConstrIC.constr_disjoint f₁ f₂ hmem₁ hmem₂ hconstr₁ hconstr₂ hdiffname vt'₁
  have hargTys_eq₂' : argTys₂ = (f₂.inputs.map Prod.snd).map (LMonoTy.subst tySubst₁) := by
    rw [hargTys_eq₂, h_subst_inputs_eq]
  have h_inputSorts_eq₂_vt1 : argTys₂.map (LMonoTy.substTyVars vt) =
      (f₂.inputs.map Prod.snd).map (LMonoTy.substTyVars vt'₁) := by
    rw [hargTys_eq₂']; simp only [List.map_map]
    congr 1; funext ⟨_, ty⟩
    exact substTyVars_subst vt tySubst₁ ty
  clear_value vt'₁
  have h_outputSort_eq₂_vt1 : LMonoTy.substTyVars vt τ = LMonoTy.substTyVars vt'₁ f₂.output := by
    rw [h_outputSort_eq₁, h_same_output]
  have hvals₁ := ListMap.values_eq_map_snd f₁.inputs
  have hvals₂ := ListMap.values_eq_map_snd f₂.inputs
  have h₁_sort : LMonoTy.substTyVars vt (LMonoTy.mkArrow' τ argTys₁) =
      LSort.mkArrow (LMonoTy.substTyVars vt'₁ f₁.output)
        (f₁.inputs.values.map (LMonoTy.substTyVars vt'₁)) := by
    rw [substTyVars_mkArrow', h_outputSort_eq₁, h_inputSorts_eq₁, hvals₁]
  have h₂_sort : LMonoTy.substTyVars vt (LMonoTy.mkArrow' τ argTys₂) =
      LSort.mkArrow (LMonoTy.substTyVars vt'₁ f₂.output)
        (f₂.inputs.values.map (LMonoTy.substTyVars vt'₁)) := by
    rw [substTyVars_mkArrow', h_outputSort_eq₂_vt1, h_inputSorts_eq₂_vt1, hvals₂]
  have h_output_sorts_eq := congrArg (LMonoTy.substTyVars vt'₁) h_same_output
  let dArgs₁ := denoteArgs tcInterp opInterp fvarVal vt .nil args₁ argTys₁ h_args₁
  let dArgs₂ := denoteArgs tcInterp opInterp fvarVal vt .nil args₂ argTys₂ h_args₂
  have h_convert₁ := applyArgs_cast_eq
    (substTyVars_mkArrow' vt τ argTys₁) h₁_sort
    (hvals₁ ▸ h_inputSorts_eq₁) h_outputSort_eq₁
    (opInterp f₁.name.name (LMonoTy.substTyVars vt (LMonoTy.mkArrow' τ argTys₁))) dArgs₁
  have h_convert₂ := applyArgs_cast_eq
    (substTyVars_mkArrow' vt τ argTys₂) h₂_sort
    (hvals₂ ▸ h_inputSorts_eq₂_vt1) h_outputSort_eq₂_vt1
    (opInterp f₂.name.name (LMonoTy.substTyVars vt (LMonoTy.mkArrow' τ argTys₂))) dArgs₂
  specialize hdisj h_output_sorts_eq
    (HList.cast (hvals₁ ▸ h_inputSorts_eq₁) dArgs₁)
    (HList.cast (hvals₂ ▸ h_inputSorts_eq₂_vt1) dArgs₂)
  grind only
