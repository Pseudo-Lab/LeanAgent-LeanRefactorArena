theorem subset_inp [Fintype P] {ps : Set P} {inp1 inp2 : P → Bool} {s1 : State P M S}
    (he : InpEqOn ps inp1 inp2) (hr : a.CanReachVia ps (a.start inp1) s1) :
    ∃ s2, a.CanReachVia ps (a.start inp2) s2 ∧ s2.proc = s1.proc := by
  obtain ⟨xs, h_mtr, h_xs⟩ := hr
  obtain ⟨ss, _, h_ss0, _, _⟩ := LTS.Execution.of_mTr h_mtr
  suffices h_inv : ∀ k, (_ : k ≤ xs.length) →
    ∃ s2, a.lts.MTr (a.start inp2) (xs.take k) s2 ∧ s2.proc = ss[k].proc ∧
      ∀ m, m.dest ∈ ps → s2.msgs.count m = ss[k].msgs.count m by
    obtain ⟨s2, _⟩ := h_inv xs.length (by simp)
    use s2, ?_, by grind only [#32f5]
    use xs, by grind
  intro k h_k
  induction k
  case zero =>
    use a.start inp2, by grind [LTS.MTr], by grind [Algorithm.start]
    intro m h_m
    simp only [h_ss0, Algorithm.start, count_map, Message.ext_iff]
    congr
    grind [InpEqOn]
  case succ k h_ind =>
    obtain ⟨s2, h_mtr, h_proc, h_msgs⟩ := h_ind (by grind)
    obtain (_ | ⟨m, h_m⟩) := Option.eq_none_or_eq_some xs[k]
    · use s2, ?_, ?_, ?_
      · have h_tr : a.lts.Tr s2 xs[k] s2 := by grind [Algorithm.lts]
        grind [List.take_add_one, LTS.MTr.stepR (lts := a.lts) h_mtr h_tr]
      · grind [Algorithm.tr_none]
      · grind [Algorithm.tr_none]
    · obtain ⟨_, h_k1⟩ : m ∈ ss[k].msgs ∧ ss[k + 1] = a.recvMsg m ss[k] := by grind [Algorithm.lts]
      use a.recvMsg m s2, ?_, ?_, ?_
      · have := List.forall_mem_iff_forall_getElem.mp <| List.forall_iff_forall_mem.mp h_xs
        have h_tr : a.lts.Tr s2 xs[k] (a.recvMsg m s2) := by
          grind [Algorithm.lts, DestIn, one_le_count_iff_mem]
        grind [List.take_add_one, LTS.MTr.stepR (lts := a.lts) h_mtr h_tr]
      · grind [Algorithm.recvMsg]
      · intro m1 h_m1
        by_cases h1 : m1 = m
        · simp [h_k1, Algorithm.recvMsg, h_proc, h1, count_erase_self]
          grind
        · simp [h_k1, Algorithm.recvMsg, h_proc, count_erase_of_ne h1]
          grind
