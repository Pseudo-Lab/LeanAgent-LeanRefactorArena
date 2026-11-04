theorem of_consensus [Fintype P] (f : ℕ) (hf : f < card P)
    (hc : a.Consensus f) : a.PseudoConsensus f := by
  refine ⟨hc.1, ?_⟩
  rintro inp s ⟨xl, hx⟩ ps hps
  let seg := a.fairSegActions (a.simpleDeliver ps) ps s
  let xs := xl ++ω seg.flatten
  have hd := simpleDeliver_fair (a := a) ps
  obtain ⟨ss, he, hs, _, _, _, fair⟩ := fair_omegaExecution hd s trivial
  obtain ⟨zz, hz, h0, _, ht⟩ := LTS.OmegaExecution.append hx he hs
  have dest := omega_forall_actions hd s trivial (simpleDeliver_forallActions ps) (by simp [DestIn])
  have keep : ∀ p ∈ ps, ProcFair p zz xs := by
    intro p hp
    apply (Algorithm.drop_procFair_iff hz p xl.length).mp
    simpa [xs, ht, drop_append_of_ge_length] using fair p hp
  have hb : numProcFaulty zz xs ≤ f := by
    apply (numProcFaulty_le_not_procFair keep).trans
    exact Nat.sub_le_iff_le_add'.2 (Nat.le_add_of_sub_le hps)
  have adm : a.AdmissibleRun inp f zz xs := by
    refine ⟨h0, hz, ?_, hb⟩
    intro p
    by_cases hp : ProcFair p zz xs
    · exact Or.inr hp
    · apply Or.inl
      have np : p ∉ ps := mt (keep p) hp
      obtain ⟨m, hm, n, _, stay⟩ := Algorithm.not_fair_stay_enabled hz hp
      refine ⟨n + xl.length, ⟨m, (stay _ (by omega)).1, hm⟩, ?_⟩
      intro j hj m' hj'
      simp only [xs, get_append_right', show xl.length ≤ j by omega] at hj'
      have d := dest (j - xl.length)
      rw [hj'] at d
      rintro rfl
      exact np d
  obtain ⟨p, hp⟩ := not_procFaulty_of_numProcFaulty (hb.trans_lt hf)
  obtain ⟨n, b, h⟩ := Or.resolve_left (hc.2 inp zz xs adm p) hp
  refine ⟨ss n, b, ⟨seg.flatten.extract 0 n, ?_, ?_⟩, ?_⟩
  · simpa [hs] using he.extract_mTr (Nat.zero_le n)
  · simp [extract_eq_take, List.forall_iff_forall_mem, List.forall_mem_iff_getElem]
    grind
  · apply Algorithm.decided_stable (a := a) (show (zz n).Decided b from ⟨p, h⟩)
    use xs.extract n (n + xl.length)
    rw [← ht]
    exact hz.extract_mTr (Nat.le_add_right _ _)