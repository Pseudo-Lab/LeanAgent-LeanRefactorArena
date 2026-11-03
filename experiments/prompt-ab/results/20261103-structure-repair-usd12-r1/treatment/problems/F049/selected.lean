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
  have aux (F : Finset ((localColim s₀)[[ℕ]])[[ℕ]].Sentenceω)
      (hc : ∀ τ ∈ F, τ ∈ T ∨ τ.not ∈ T) :
      ∃ σ w, ∀ τ ∈ F, realizeWith σ w τ (Empty.elim : Empty → M) Fin.elim0 ↔ τ ∈ T := by
    let sign := fun τ => if τ ∈ T then τ else τ.not
    obtain ⟨σ, w, hr⟩ := exists_body_of_subset hM (F.image sign) (by
      intro τ hτ
      obtain ⟨τ, ht, rfl⟩ := Finset.mem_image.mp hτ
      dsimp [sign]
      split_ifs with h
      · exact h
      · exact (hc τ ht).resolve_left h)
    refine ⟨σ, w, fun τ ht => ?_⟩
    have h := hr _ (Finset.mem_image.mpr ⟨τ, ht, rfl⟩)
    dsimp [sign] at h
    split_ifs at h with ht
    · exact iff_of_true h ht
    · exact iff_of_false h ht
  obtain ⟨σ, w, hr⟩ := aux {_, _, _} (by
    simp only [Finset.mem_insert, Finset.mem_singleton, forall_eq_or_imp, forall_eq]
    exact ⟨sa, sb, sc⟩)
  simp only [Finset.mem_insert, Finset.mem_singleton, forall_eq_or_imp, forall_eq] at hr
  obtain ⟨ha, hb, hc⟩ := hr
  simp only [BoundedFormulaω.mapLanguage, BoundedFormulaω.realize_imp,
    ihφ hφmem ts, ihψ hψmem ts]
  apply (imp_congr ha.symm hb.symm).trans
  apply Iff.trans ?_ hc
  simp only [realize_schemaFormulaSentence_iff]
  rfl
