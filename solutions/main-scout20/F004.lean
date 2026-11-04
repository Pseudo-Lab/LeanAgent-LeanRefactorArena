theorem callOfLFunc_eraseMetadata_congr
    (F : @Factory Tbase) (e₁ e₂ : LExpr Tbase.mono) (aPA : Bool)
    (h_eM : e₁.eraseMetadata = e₂.eraseMetadata) :
    match F.callOfLFunc e₁ (allowPartialApp := aPA), F.callOfLFunc e₂ (allowPartialApp := aPA) with
    | some (op₁, args₁, f₁), some (op₂, args₂, f₂) =>
        f₁ = f₂ ∧ args₁.map LExpr.eraseMetadata = args₂.map LExpr.eraseMetadata
        ∧ op₁.eraseMetadata = op₂.eraseMetadata
    | none, none => True
    | _, _ => False := by
  have h := getLFuncCall_eraseMetadata_congr e₁ e₂ h_eM
  unfold Factory.callOfLFunc
  revert h
  obtain ⟨op₁, args₁⟩ := getLFuncCall e₁
  obtain ⟨op₂, args₂⟩ := getLFuncCall e₂
  intro h
  cases EMEquiv.of_eraseMetadata_eq _ _ h.1 <;> try trivial
  rename_i m₁ n t m₂
  have hl := congrArg List.length h.2
  simp at hl
  simp only [hl]
  cases F[n.name]? with
  | none => trivial
  | some f =>
    dsimp
    cases (if aPA then Nat.ble args₂.length f.inputs.length else args₂.length == f.inputs.length) <;>
      simp [h]
