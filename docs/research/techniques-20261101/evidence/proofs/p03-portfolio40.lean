theorem InitsUpdatesComm
  {P : PureExpr} {σ σ' σ'' : SemanticStore P}
  {ks ks' : List P.Ident} {vs vs' : List P.Expr} :
  UpdateStates σ ks vs σ' →
  InitStates σ' ks' vs' σ'' →
  ∃ σ₁,
    σ₁ = (updatedStates σ ks' vs') ∧
    InitStates σ ks' vs' σ₁ ∧
    UpdateStates σ₁ ks vs σ'' := by
  intro u i
  have hl := InitStatesLength i
  have hl' := UpdateStatesLength u
  refine ⟨_, rfl, updatedStatesInit hl
    (UpdateStatesNotDefMonotone' (InitStatesNotDefined i) u) (InitStatesNodup i), ?_⟩
  cases InitStatesUpdated i
  cases UpdateStatesUpdated u
  unfold updatedStates
  rw [updatedStatesComm]
  · exact updatedStatesUpdate hl'
      (updatedStatesDefMonotone (UpdateStatesDefined' u))
  · simp_all [List.unzip_zip]
    intro k hk hk'
    simpa [InitStatesNotDefined i k hk'] using UpdateStatesDefined u k hk
