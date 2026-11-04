theorem reduction_perfectCompleteness :
    (reduction R deg D oSpec).perfectCompleteness init impl
      (inputRelation R deg D) (outputRelation R deg) := by
  simp only [Reduction.perfectCompleteness, Reduction.completeness, ENNReal.coe_zero, tsub_zero]
  intro ⟨target, oStmt⟩ () hValid
  simp only [inputRelation, Set.mem_setOf_eq] at hValid
  simp only [reduction, Reduction.run, Prover.run, Verifier.run, prover, verifier,
    Prover.runToRound, Prover.processRound, Fin.induction_two, pSpec,
    bind_pure_comp, Functor.map_map, Function.comp]
  split <;> rename_i hDir0
  · exact absurd hDir0 (by decide)
  try simp only [pure_bind, map_pure, Functor.map_map, Function.comp, bind_pure_comp]
  split <;> rename_i hDir1
  swap
  · exact absurd hDir1 (by decide)
  simp only [MonadLift.monadLift, liftM, monadLift, MonadLiftT.monadLift,
    OracleComp.liftComp_pure, pure_bind, map_pure, Functor.map_map, Function.comp,
    bind_pure_comp, Transcript.concat, Fin.snoc_last, Fin.snoc_castSucc,
    guard, if_pos hValid]
  rw [ge_iff_le, one_le_probEvent_iff, probEvent_eq_one_iff]
  constructor
  all_goals
    first
    | rw [OptionT.probFailure_eq, OptionT.run_mk]
      simp only [probFailure_eq_zero, zero_add]
      apply probOutput_eq_zero_of_not_mem_support
      simp only [support_bind, Set.mem_iUnion, not_exists]
      intro s _ hmem
      simp only [StateT.run'_eq, support_map, Set.mem_image] at hmem
      obtain ⟨⟨_, s'⟩, hmem, rfl⟩ := hmem
    | intro x hmem
      rw [OptionT.mem_support_iff] at hmem
      simp only [OptionT.run_mk, support_bind, Set.mem_iUnion] at hmem
      rcases hmem with ⟨s, _, hmem⟩
      simp only [StateT.run'_eq, support_map, Set.mem_image] at hmem
      rcases hmem with ⟨⟨_, s'⟩, hmem, rfl⟩
  all_goals
    erw [simulateQ_bind, StateT.run_bind, mem_support_bind_iff] at hmem
    rcases hmem with ⟨⟨x, s''⟩, hx, hs⟩
    erw [simulateQ_map, StateT.run_map] at hx
    simp only [support_map, Set.mem_image] at hx
    rcases hx with ⟨⟨val, s₀⟩, hval, heq⟩
    obtain ⟨rfl, rfl⟩ := Prod.mk.inj heq
    clear heq
    erw [simulateQ_bind, StateT.run_bind, mem_support_bind_iff] at hs
    rcases hs with ⟨⟨y, s'''⟩, hy, hs⟩
    erw [simulateQ_map, simulateQ_map, StateT.run_map] at hy
    simp only [support_map, Set.mem_image] at hy
    rcases hy with ⟨⟨val2, s₁⟩, hval2, heq2⟩
    obtain ⟨rfl, rfl⟩ := Prod.mk.inj heq2
    clear heq2
    erw [simulateQ_bind, StateT.run_bind, mem_support_bind_iff] at hval
    rcases hval with ⟨⟨chal_res, s₂⟩, hchal, hval⟩
    erw [simulateQ_bind, simulateQ_map, simulateQ_pure] at hchal
    simp only [map_pure, pure_bind] at hchal
    erw [simulateQ_map, StateT.run_map] at hchal
    simp only [support_map, Set.mem_image] at hchal
    rcases hchal with ⟨⟨inner_val, s_inner⟩, hinner, heq_c⟩
    clear hinner
    obtain ⟨rfl, rfl⟩ := Prod.mk.inj heq_c
    clear heq_c
    erw [simulateQ_pure] at hval
    simp only [StateT.run_pure, support_pure, Set.mem_singleton_iff] at hval
    obtain ⟨rfl, rfl⟩ := Prod.mk.inj hval
    clear hval
    rw [Finset.sum_map] at hValid
    simp [QueryImpl.addLift_def, QueryImpl.liftTarget_apply,
      QueryImpl.add_apply_inl, QueryImpl.add_apply_inr,
      simulateQ_query, simulateQ_pure, simulateQ_bind, simulateQ_map,
      QueryImpl.simulateQ_add_liftComp_right, QueryImpl.simulateQ_add_liftComp_left,
      OracleComp.liftComp_map, OracleComp.liftComp_pure,
      Function.comp, OracleQuery.cont, OracleQuery.input_query,
      StateT.run_bind, StateT.run_map, StateT.run_pure,
      support_map, support_pure, Fin.snoc, hValid] at hval2
    rcases hval2 with ⟨_, ⟨_, rfl⟩, _, rfl⟩
    simp only [Option.getM, pure_bind] at hs
    erw [simulateQ_pure] at hs
    simp only [StateT.run_pure, support_pure, Set.mem_singleton_iff] at hs
    first
    | exfalso; simpa using congr_arg Prod.fst hs
    | cases hs
      simp [outputRelation]
