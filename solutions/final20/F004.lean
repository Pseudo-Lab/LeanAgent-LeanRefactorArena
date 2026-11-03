theorem callOfLFunc_eraseMetadata_congr
    (F : @Factory Tbase) (e₁ e₂ : LExpr Tbase.mono) (aPA : Bool)
    (h_eM : e₁.eraseMetadata = e₂.eraseMetadata) :
    match F.callOfLFunc e₁ (allowPartialApp := aPA), F.callOfLFunc e₂ (allowPartialApp := aPA) with
    | some (op₁, args₁, f₁), some (op₂, args₂, f₂) =>
        f₁ = f₂ ∧ args₁.map LExpr.eraseMetadata = args₂.map LExpr.eraseMetadata
        ∧ op₁.eraseMetadata = op₂.eraseMetadata
    | none, none => True
    | _, _ => False := by
  obtain ⟨h_op, h_args⟩ := getLFuncCall_eraseMetadata_congr e₁ e₂ h_eM
  unfold Factory.callOfLFunc
  generalize getLFuncCall e₁ = r₁, getLFuncCall e₂ = r₂ at *
  cases r₁
  cases r₂
  cases EMEquiv.of_eraseMetadata_eq _ _ h_op with
  | @op _ n =>
    dsimp only
    cases F[n.name]?
    · constructor
    · rw [← List.length_map LExpr.eraseMetadata, h_args, List.length_map]
      dsimp only
      cases (if aPA then _ else _) <;> repeat constructor
      all_goals assumption
  | _ => constructor
