theorem InitsUpdatesComm
  {P : PureExpr} {σ σ' σ'' : SemanticStore P}
  {ks ks' : List P.Ident} {vs vs' : List P.Expr} :
  UpdateStates σ ks vs σ' →
  InitStates σ' ks' vs' σ'' →
  ∃ σ₁,
    σ₁ = (updatedStates σ ks' vs') ∧
    InitStates σ ks' vs' σ₁ ∧
    UpdateStates σ₁ ks vs σ'' := by
  intro hup hi
  refine ⟨_, rfl, updatedStatesInit (InitStatesLength hi) (UpdateStatesNotDefMonotone' (InitStatesNotDefined hi) hup) $ InitStatesNodup hi, ?_⟩
  cases InitStatesUpdated hi
  cases UpdateStatesUpdated hup
  delta updatedStates
  rw [updatedStatesComm]
  apply updatedStatesUpdate $ UpdateStatesLength hup
  apply updatedStatesDefMonotone
  apply UpdateStatesDefined' hup
  simp [List.unzip_zip, UpdateStatesLength hup, InitStatesLength hi]
  intro _ hk hk'
  cases InitStatesNotDefined hi _ hk' ▸ UpdateStatesDefined hup _ hk
