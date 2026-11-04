private theorem schemaTruthStage_imp
    (hM : Cardinal.beth (Ordinal.omega 1) ≤ Cardinal.mk M) (k : ℕ) {n : ℕ}
    (φ ψ' : (Llocal s₀ (k + 1)).BoundedFormulaω Empty n)
    (ihφ : SchemaTruthStage hM k φ) (ihψ : SchemaTruthStage hM k ψ') :
    SchemaTruthStage hM k (φ.imp ψ') := by
  classical
  let : (localColim s₀).Structure M := localColimStructure s₀
  intro hmem ts
  have hφ := bfSubformulas_subset_Γlocal_succ s₀ hmem (Set.mem_insert _ _)
  have hψ := bfSubformulas_subset_Γlocal_succ s₀ hmem (Set.mem_insert_of_mem _ rfl)
  simp only [BoundedFormulaω.mapLanguage, BoundedFormulaω.realize_imp, ihφ hφ ts, ihψ hψ ts]
  let S χ := schemaFormulaSentence
    (BoundedFormulaω.mapLanguage (LlocalInclusion s₀ (k + 1)) χ) ts
  let T := schemaCompletionTheory (schemaEnumeration s₀) hM
  let sign χ := if S χ ∈ T then S χ else (S χ).not
  have hs χ (hm : ⟨n, χ⟩ ∈ Γlocal s₀ (k + 1)) : sign χ ∈ T := by
    dsimp only [sign]
    split
    · assumption
    · exact (schemaCompletionTheory_not_mem_iff hM _
        (schemaFormulaSentence_mem_universe (toLocalColimFormula_mem_ΓlocalColim s₀ hm) ts)).2 ‹_›
  let F : Finset _ := {sign φ, sign ψ', sign (φ.imp ψ')}
  obtain ⟨σ, w, hb⟩ := exists_body_of_subset hM F (by
    simp [F]
    exact ⟨hs _ hφ, hs _ hψ, hs _ hmem⟩)
  have hv χ (hh : sign χ ∈ F) :
      realizeWith σ w (S χ) Empty.elim Fin.elim0 ↔ S χ ∈ T := by
    by_cases ht : S χ ∈ T <;>
      simpa [sign, ht, realizeWith_not] using hb _ hh
  simp only [S, realize_schemaFormulaSentence_iff] at hv
  simpa only [BoundedFormulaω.mapLanguage, BoundedFormulaω.realize_imp,
    hv φ (by simp [F]), hv ψ' (by simp [F])] using hv (φ.imp ψ') (by simp [F])
