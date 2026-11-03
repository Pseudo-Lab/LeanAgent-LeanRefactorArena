theorem nonUniform_step [Fintype P] (hpc1 : a.PseudoConsensus 1)
    {s : State P M S} (hr : a.Reachable inp s) (hn : a.NonUniform s) (p : P) :
    ∃ s', a.lts.CanReach s s' ∧ ∀ b, a.CanDecideWithout s' p b := by
  obtain ⟨b, h_s⟩ := canDecideWithout_exists hpc1 hr p
  obtain ⟨q, s', h_ss', h_s'⟩ := hn !b
  have hr' := Algorithm.reachable_stable hr (CanReachVia.canReach h_ss')
  obtain ⟨xs, h_mtr, h_xs'⟩ := h_ss'
  obtain ⟨ss, h_ss'⟩ := LTS.Execution.of_mTr h_mtr
  have reach_lemma (k : ℕ) (h : k < ss.length) : a.lts.CanReach s ss[k] := by
    use xs.take k
    have := LTS.Execution.split h_ss' k
    grind [LTS.Execution, LTS.Execution.to_mTr]
  have : a.CanDecideWithout s' p !b := by
    obtain ⟨b', h_b'⟩ := canDecideWithout_exists hpc1 hr' p
    grind [decided_eq_canDecideWithout hpc1 hr' h_s' h_b']
  have h_nb : ∃ n, ∃ _ : n < ss.length, a.CanDecideWithout ss[n] p !b := by grind [LTS.Execution]
  classical
  let n := Nat.find h_nb
  obtain ⟨_, _⟩ : ∃ _ : n < ss.length, a.CanDecideWithout ss[n] p !b := by grind
  use ss[n], ?_, ?_
  · grind [reach_lemma n]
  · suffices ∀ k, (_ : k ≤ n) → a.CanDecideWithout ss[k] p b by
      intro b'
      by_cases h : b' = !b
      · grind
      · simp only [Bool.not_eq_not] at h
        grind
    intro k
    induction k
    case zero => grind [LTS.Execution]
    case succ k h_ind =>
      intro h_k
      obtain ⟨_, _, _, _⟩ := h_ss'
      have h_tr : a.lts.Tr ss[k] xs[k] ss[k + 1] := by grind
      obtain (_ | ⟨m, h_m⟩) := Option.eq_none_or_eq_some xs[k]
      · grind [Algorithm.tr_none]
      · rw [h_m] at h_tr
        have hr_k : a.Reachable inp ss[k] := by
          apply Algorithm.reachable_stable hr
          grind [reach_lemma k]
        have hnb_k : ¬a.CanDecideWithout ss[k] p !b := by grind [Nat.find_min h_nb (m := k)]
        exact canDecideWithout_uniform hpc1 hr_k h_tr (h_ind (by grind)) hnb_k
