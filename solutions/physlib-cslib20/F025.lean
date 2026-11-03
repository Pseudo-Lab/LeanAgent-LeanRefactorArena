theorem of_consensus [Fintype P] (f : ℕ) (hf : f < card P)
    (hc : a.Consensus f) : a.PseudoConsensus f := by
  obtain ⟨h_safe, h_term⟩ := hc
  use h_safe
  rintro inp s ⟨xl, h_xl⟩ ps h_ps
  let xls := a.fairSegActions (a.simpleDeliver ps) ps s
  obtain ⟨ss, h_omega, h_s, _⟩ := fair_omegaExecution (simpleDeliver_fair ps) s trivial
  obtain ⟨ss', h_omega', _, _, _⟩ := LTS.OmegaExecution.append h_xl h_omega h_s
  have h_dest := omega_forall_actions (r := DestIn ps) (d := a.simpleDeliver ps)
      (simpleDeliver_fair ps) s trivial (simpleDeliver_forallActions ps) (by simp [DestIn])
  have : ∀ p, p ∈ ps → ProcFair p ss' (xl ++ω xls.flatten) := by
    intro p h_p
    rw [← Algorithm.drop_procFair_iff h_omega' p xl.length]
    grind only [drop_append_of_ge_length, = drop_zero, #09e3]
  have : FairRun ss' (xl ++ω xls.flatten) := by
    intro p
    by_cases h_f : ProcFair p ss' (xl ++ω xls.flatten)
    · grind
    · obtain ⟨m, _, n, _, _⟩ := Algorithm.not_fair_stay_enabled h_omega' h_f
      suffices ProcFaulty p ss' (xl ++ω xls.flatten) by grind
      use n + xl.length, by grind only [#bd9e, #4bb0]
      intro k h_k m' h_m'
      have : xls.flatten (k - xl.length) = some m' := by grind only [get_append_right']
      grind only [DestIn, #9e35, #7634]
  have : numProcFaulty ss' (xl ++ω xls.flatten) ≤ f := by
    suffices numProcFaulty ss' (xl ++ω xls.flatten) ≤ card P - ps.ncard by grind only [#5a28]
    apply numProcFaulty_le_not_procFair
    assumption
  have h_adm : a.AdmissibleRun inp f ss' (xl ++ω xls.flatten) := by grind only [Algorithm.AdmissibleRun]
  have hf' : numProcFaulty ss' (xl ++ω xls.flatten) < card P := by grind
  obtain ⟨p, _⟩ := not_procFaulty_of_numProcFaulty hf'
  obtain ⟨n, b, _⟩ : ∃ n b, (ss' n).ProcDecided p b := by
    grind only [ProcTermination, #d702, #2985, h_term inp ss' (xl ++ω xls.flatten) h_adm p]
  let m := n + xl.length
  use ss' m, b
  split_ands
  · use (xl ++ω xls.flatten).extract xl.length m, by grind only [LTS.OmegaExecution.extract_mTr]
    simp [extract_append_right_right, extract_eq_take,
      List.forall_iff_forall_mem, List.forall_mem_iff_getElem]
    grind only [#9e35]
  · have : (ss' n).Decided b := by use p
    suffices a.lts.CanReach (ss' n) (ss' m) by grind only [!Algorithm.decided_stable]
    use (xl ++ω xls.flatten).extract n m
    grind only [LTS.OmegaExecution.extract_mTr]
