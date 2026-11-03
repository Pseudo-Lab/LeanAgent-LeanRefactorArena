theorem subset_inp [Fintype P] {ps : Set P} {inp1 inp2 : P → Bool} {s1 : State P M S}
    (he : InpEqOn ps inp1 inp2) (hr : a.CanReachVia ps (a.start inp1) s1) :
    ∃ s2, a.CanReachVia ps (a.start inp2) s2 ∧ s2.proc = s1.proc := by
  suffices sim : ∀ {s u xs}, a.lts.MTr s xs u →
      ∀ t, State.proc t = s.proc →
      (∀ m, m.dest ∈ ps → t.msgs.count m = s.msgs.count m) →
      xs.Forall (DestIn ps) →
      ∃ v, a.CanReachVia ps t v ∧ v.proc = u.proc by
    obtain ⟨xs, h, hx⟩ := hr
    refine sim h _ rfl ?_ hx
    intro m hm
    simp only [Algorithm.start, count_map]
    congr
    grind only [InpEqOn]
  intro s u xs h
  induction h <;> intro t hp hm hx
  next =>
    exact ⟨t, refl ps t, hp⟩
  next s x u xs v ht h ih =>
    rw [List.forall_cons] at hx
    obtain ⟨hx, hxs⟩ := hx
    cases x with
    | none =>
      cases ht
      exact ih t hp hm hxs
    | some m =>
      obtain ⟨hmem, rfl⟩ := ht
      obtain ⟨w, hw, hwp⟩ := ih (a.recvMsg m t)
        (by simp only [Algorithm.recvMsg, hp])
        (by
          intro n hn
          rcases eq_or_ne n m with rfl | hnm <;>
            simp [Algorithm.recvMsg, count_erase_of_ne, *]) hxs
      exact ⟨w, stepL hx ⟨by
        rwa [← one_le_count_iff_mem, hm m hx, one_le_count_iff_mem], rfl⟩ hw, hwp⟩