theorem nonUniform_step [Fintype P] (hpc1 : a.PseudoConsensus 1)
    {s : State P M S} (hr : a.Reachable inp s) (hn : a.NonUniform s) (p : P) :
    ∃ s', a.lts.CanReach s s' ∧ ∀ b, a.CanDecideWithout s' p b := by
  obtain ⟨b, hb⟩ := canDecideWithout_exists hpc1 hr p
  obtain ⟨q, t, ⟨xs, hxs, -⟩, hd⟩ := hn !b
  clear hn
  induction xs generalizing s
  all_goals
    by_cases hnb : a.CanDecideWithout s p !b
    · use s, ⟨[], by constructor⟩
      intro c
      cases b <;> cases c <;> assumption
  · cases hxs
    exfalso
    simpa using decided_eq_canDecideWithout hpc1 hr hd hb
  rename_i x xs ih
  cases hxs
  rename_i hu hus
  obtain ⟨v, ⟨ys, hy⟩, hv⟩ :=
    ih (Algorithm.reachable_stable hr ⟨[x], by
        constructor
        assumption
        constructor⟩)
      (by
        cases x
        cases Algorithm.tr_none hu
        assumption
        exact canDecideWithout_uniform hpc1 hr hu hb hnb) hus
  use v, ⟨x :: ys, by constructor <;> assumption⟩, hv
