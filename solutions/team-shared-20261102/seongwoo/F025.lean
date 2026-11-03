theorem of_consensus [Fintype P] (f : ℕ) (hf : f < card P)
    (hc : a.Consensus f) : a.PseudoConsensus f := by
  use hc.1
  rintro inp s ⟨xl, h_xl⟩ ps h_ps
  revert hc
  let xls := a.fairSegActions (a.simpleDeliver ps) ps s
  let xs := xl ++ω xls.flatten
  rcases fair_omegaExecution (simpleDeliver_fair ps) s trivial with ⟨ss, h_omega, h_s, h_tailFair⟩
  rcases LTS.OmegaExecution.append h_xl h_omega h_s with ⟨ss', h_omega', h_start, h_prefix, h_suffix⟩
  have h_psfair : ∀ p ∈ ps, ProcFair p ss' xs := by
    clear hf h_ps h_xl
    intro p h_p
    rw [← Algorithm.drop_procFair_iff h_omega' p xl.length]
    grind [drop_append_of_ge_length]
  clear h_tailFair
  have h_dest := omega_forall_actions (r := _) (d := a.simpleDeliver ps)
      (simpleDeliver_fair ps) s trivial (simpleDeliver_forallActions ps) (by simp [DestIn])
  have h_fair : FairRun ss' xs := by
    clear hf h_ps h_xl h_s h_start h_prefix h_suffix h_omega
    intro p
    by_cases h_f : ProcFair p ss' xs
    · grind only
    · rcases Algorithm.not_fair_stay_enabled h_omega' h_f with ⟨m, _, n, _, _⟩
      suffices ProcFaulty p ss' xs by grind only
      use n + xl.length, by grind only
      intro k h_k m' h_m'
      simp only [xs, get_append_right', show xl.length ≤ k by omega] at h_m'
      grind only [DestIn]
  have h_bound : numProcFaulty ss' xs ≤ f := by
    suffices numProcFaulty ss' xs ≤ card P - ps.ncard by omega
    apply numProcFaulty_le_not_procFair
    assumption
  have h_adm : a.AdmissibleRun inp f ss' xs := by
    clear h_dest h_psfair h_prefix h_suffix h_omega
    grind only [Algorithm.AdmissibleRun]
  clear h_psfair h_fair h_xl h_ps h_start h_prefix
  rcases not_procFaulty_of_numProcFaulty (h_bound.trans_lt hf) with ⟨p, hp⟩
  intro hc
  obtain ⟨n, b, h_dec⟩ : ∃ n b, (ss' n).ProcDecided p b := by
    clear h_dest h_s h_suffix h_omega' h_omega
    grind only [ProcTermination, hc.2 inp ss' xs h_adm p]
  clear hc h_adm h_bound hp hf
  use ss n, b
  constructor
  · use xls.flatten.extract 0 n, by grind only [LTS.OmegaExecution.extract_mTr]
    simp [extract_eq_take, List.forall_iff_forall_mem, List.forall_mem_iff_getElem]
    grind
  · have : (ss' n).Decided b := by use p
    clear h_dest h_s h_dec h_omega
    suffices a.lts.CanReach (ss' n) (ss n) by grind only [Algorithm.decided_stable]
    use xs.extract n (n + xl.length)
    grind [LTS.OmegaExecution.extract_mTr]
