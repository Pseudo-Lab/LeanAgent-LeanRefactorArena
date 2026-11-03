private theorem schemaTruthStage_imp
    (hM : Cardinal.beth (Ordinal.omega 1) ≤ Cardinal.mk M) (k : ℕ) {n : ℕ}
    (φ ψ' : (Llocal s₀ (k + 1)).BoundedFormulaω Empty n)
    (ihφ : SchemaTruthStage hM k φ) (ihψ : SchemaTruthStage hM k ψ') :
    SchemaTruthStage hM k (φ.imp ψ') := by
  let : (localColim s₀).Structure M := localColimStructure s₀
  intro hmem ts
  classical
  have hφmem := bfSubformulas_subset_Γlocal_succ s₀ hmem (Set.mem_insert _ _)
  have hψmem := bfSubformulas_subset_Γlocal_succ s₀ hmem (Set.mem_insert_of_mem _ rfl)
  have spec := schemaCompletionTheorySpec (s₀ := s₀) hM
  have sa := spec.complete_on_universe _ (schemaFormulaSentence_mem_universe
    (toLocalColimFormula_mem_ΓlocalColim s₀ hφmem) ts)
  have sb := spec.complete_on_universe _ (schemaFormulaSentence_mem_universe
    (toLocalColimFormula_mem_ΓlocalColim s₀ hψmem) ts)
  have sc := spec.complete_on_universe _ (schemaFormulaSentence_mem_universe
    (toLocalColimFormula_mem_ΓlocalColim s₀ hmem) ts)
  let T := schemaCompletionTheory (schemaEnumeration s₀) hM
  let r := fun σ w (τ : ((localColim s₀)[[ℕ]])[[ℕ]].Sentenceω) =>
    realizeWith σ w τ (Empty.elim : Empty → M) Fin.elim0
  have aux (A B C)
      (sa : A ∈ T ∨ A.not ∈ T) (sb : B ∈ T ∨ B.not ∈ T) (sc : C ∈ T ∨ C.not ∈ T)
      (sem : ∀ σ w, r σ w C ↔ (r σ w A → r σ w B)) :
      (A ∈ T → B ∈ T) ↔ C ∈ T := by
    let sign := fun τ => if τ ∈ T then τ else τ.not
    obtain ⟨σ, w, hr⟩ := exists_body_of_subset hM {sign A, sign B, sign C} (by
      simp only [Finset.mem_insert, Finset.mem_singleton, forall_eq_or_imp, forall_eq]
      refine ⟨?_, ?_, ?_⟩ <;> dsimp [sign] <;> split_ifs with h
      all_goals first | exact h | exact sa.resolve_left h | exact sb.resolve_left h | exact sc.resolve_left h)
    have bridge (τ) (h : r σ w (sign τ)) : r σ w τ ↔ τ ∈ T := by
      unfold sign at h
      split_ifs at h with ht
      · exact iff_of_true h ht
      · exact iff_of_false h ht
    simpa only [bridge A (hr _ (by simp)), bridge B (hr _ (by simp)),
      bridge C (hr _ (by simp))] using (sem σ w).symm
  simp only [BoundedFormulaω.mapLanguage, BoundedFormulaω.realize_imp,
    ihφ hφmem ts, ihψ hψmem ts]
  exact aux _ _ _ sa sb sc (fun σ w => by
    simp only [r, realize_schemaFormulaSentence_iff]
    rfl)
