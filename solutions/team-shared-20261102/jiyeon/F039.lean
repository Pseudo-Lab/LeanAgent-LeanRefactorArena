theorem reduction_perfectCompleteness :
    (reduction R deg D oSpec).perfectCompleteness init impl
      (inputRelation R deg D) (outputRelation R deg) := by
  simp only [Reduction.perfectCompleteness, Reduction.completeness, ENNReal.coe_zero, tsub_zero]
  intro ⟨target, oStmt⟩ () hValid
  simp only [inputRelation, Set.mem_setOf_eq] at hValid
  simp only [reduction, Reduction.run, Prover.run, Verifier.run, prover, verifier,
    Prover.runToRound, Prover.processRound, Fin.induction_two, pSpec,
    bind_pure_comp, Function.comp]
  split <;> rename_i hDir0
  · exact absurd hDir0 (by decide)
  try simp only [pure_bind, map_pure, Functor.map_map, Function.comp, bind_pure_comp]
  split <;> rename_i hDir1
  swap
  · exact absurd hDir1 (by decide)
  simp only [MonadLift.monadLift, liftM, monadLift, MonadLiftT.monadLift,
    OracleComp.liftComp_pure, map_pure,     bind_pure_comp, Transcript.concat,     guard, if_pos hValid]
  rw [ge_iff_le, one_le_probEvent_iff, probEvent_eq_one_iff]
  constructor
  all_goals first
    | (rw [OptionT.probFailure_eq, OptionT.run_mk]
       simp only [probFailure_eq_zero, zero_add]
       apply probOutput_eq_zero_of_not_mem_support
       simp only [support_bind, Set.mem_iUnion, not_exists]
       intro s _ hmem)
    | (intro x hx
       rw [OptionT.mem_support_iff] at hx
       simp only [OptionT.run_mk, support_bind, Set.mem_iUnion] at hx
       obtain ⟨s, _, hmem⟩ := hx)
  all_goals
    simp only [StateT.run'_eq, support_map, Set.mem_image] at hmem
    obtain ⟨⟨_, s'⟩, hmem, rfl⟩ := hmem
    erw [simulateQ_bind, StateT.run_bind] at hmem
    rw [mem_support_bind_iff] at hmem
    obtain ⟨⟨x, s''⟩, hx, hs⟩ := hmem
    erw [simulateQ_map] at hx
    rw [StateT.run_map] at hx
    simp only [support_map, Set.mem_image] at hx
    obtain ⟨⟨val, s₀⟩, hval, heq⟩ := hx
    obtain ⟨rfl, rfl⟩ := Prod.mk.inj heq
    erw [simulateQ_bind, StateT.run_bind] at hs
    rw [mem_support_bind_iff] at hs
    obtain ⟨⟨y, s'''⟩, hy, hs⟩ := hs
    erw [simulateQ_map, simulateQ_map] at hy
    rw [StateT.run_map] at hy
    simp only [support_map, Set.mem_image] at hy
    obtain ⟨⟨val2, s₁⟩, hval2, heq2⟩ := hy
    obtain ⟨rfl, rfl⟩ := Prod.mk.inj heq2
    dsimp only [] at hs
    rcases val2 with _ | ⟨out⟩
  all_goals
    try (simp only [Option.getM] at hs
         erw [simulateQ_pure] at hs
         simp only [StateT.run_pure, support_pure, Set.mem_singleton_iff] at hs
         cases hs)
  all_goals
    have hv := support_simulateQ_run'_subset (n := ProbComp) (impl.addLift challengeQueryImpl) _ s
      (show val ∈ _root_.support (StateT.run' (m := ProbComp) (simulateQ (impl.addLift challengeQueryImpl) _) s) from by
        rw [StateT.run'_eq, support_map]
        exact ⟨_, hval, rfl⟩)
    rw [mem_support_bind_iff] at hv
    obtain ⟨chal, hchal, hv⟩ := hv
    erw [mem_support_bind_iff] at hchal
    obtain ⟨discr, hd, hc⟩ := hchal
    erw [support_map, support_pure] at hd
    obtain ⟨_, rfl, rfl⟩ := hd
    erw [support_map] at hc
    change ∃ r, _ ∧ _ = chal at hc
    obtain ⟨r, _, rfl⟩ := hc
    simp only [OracleComp.liftComp_pure, map_pure, support_pure, Set.mem_singleton_iff] at hv
    subst val
    simp only [QueryImpl.addLift_def,                                     OracleQuery.input_query,
                  Fin.snoc] at hval2
    norm_num at hval2
    rw [Finset.sum_map] at hValid
    simp only [apply_ite, OptionT.run_pure] at hval2
    erw [if_pos hValid] at hval2
    simp only [simulateQ_pure,
      StateT.run_pure, support_pure, Set.mem_singleton_iff] at hval2
    first
    | solve | simp at hval2
    | (obtain ⟨_, ⟨_, rfl⟩, _, rfl⟩ := hval2
       simp only [Set.mem_setOf_eq, outputRelation]
       constructor <;> simp)
