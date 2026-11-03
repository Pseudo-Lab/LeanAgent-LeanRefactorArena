theorem parallel_diamond : Diamond ((· ⭢ₚ ·) : Term Var → Term Var → Prop) := by
  intros t t1 t2 tpt1
  revert t2
  induction tpt1 <;> intros t2 tpt2
  case fvar x => exact ⟨t2, by grind⟩
  case abs s1 s2' xs mem ih =>
    cases tpt2
    case abs t2' xs' mem' =>
      have ⟨x, qx⟩ := fresh_exists (xs ∪ xs' ∪ free_union [fv] Var)
      simp only [Finset.union_assoc, Finset.mem_union, not_or] at qx
      have ⟨q1, q2, _⟩ := qx
      have ⟨t', _⟩ := ih x q1 (mem' _ q2)
      exists abs (t' ^* x)
      constructor
      <;> [let z := s2' ^ fvar x; let z := t2' ^ fvar x]
      <;> apply Parallel.abs (free_union [fv] Var) <;> grind only [→ para_lc_r, usr subst_intro, = close_open_to_subst, → lc_refl, LC.fvar, para_subst]
  case beta s1 s1' s2 s2' xs mem ps ih1 ih2 =>
    cases tpt2
    case app u2 u2' s1pu2 s2pu2' =>
      cases s1pu2
      case abs s1'' xs' mem' =>
        have ⟨x, qx⟩ := fresh_exists (xs ∪ xs' ∪ free_union [fv] Var)
        simp only [Finset.union_assoc, Finset.mem_union, not_or] at qx
        obtain ⟨q1, q2, _⟩ := qx
        have ⟨t', _⟩ := ih2 s2pu2'
        have ⟨t'', _⟩ := @ih1 x q1 _ (mem' _ q2)
        exists (t'' ^* x) ^ t'
        constructor
        · #adaptation_note
          /-- Moving from `nightly-2025-09-15` to `nightly-2025-10-19`, the grind_pattern for
          subst_intro (defined in Properties.lean) stopped working here. -/
          grind only [→ para_lc_r, usr subst_intro, = close_open_to_subst, para_subst]
        · apply Parallel.beta (free_union [fv] Var) <;> grind only [→ para_lc_r, usr subst_intro, = close_open_to_subst, → lc_refl, LC.fvar, para_subst]
    case beta u1' u2' xs' mem' s2pu2' =>
      have ⟨x, qx⟩ := fresh_exists (xs ∪ xs' ∪ free_union [fv] Var)
      simp only [Finset.union_assoc, Finset.mem_union, not_or] at qx
      have ⟨q1, q2, _⟩ := qx
      have ⟨t', _⟩ := ih2 s2pu2'
      have ⟨t'', _⟩ := @ih1 x q1 _ (mem' _ q2)
      refine ⟨t''[x := t'], ?_⟩
      grind only [usr subst_intro, para_subst]
  case app s1 s1' s2 s2' s1ps1' _ ih1 ih2  =>
    cases tpt2
    case app u1 u2' s1 s2 =>
      have ⟨l, _, _⟩ := ih1 s1
      have ⟨r, _, _⟩ := ih2 s2
      exact ⟨app l r, by grind⟩
    case beta t1' u1' u2' xs mem s2pu2' =>
      cases s1ps1'
      case abs s1'' xs' mem' =>
        have ⟨x, qx⟩ := fresh_exists (xs ∪ xs' ∪ free_union [fv] Var)
        simp only [Finset.union_assoc, Finset.mem_union, not_or] at qx
        obtain ⟨q1, q2, _⟩ := qx
        have ⟨t', qt'_l, qt'_r⟩ := ih2 s2pu2'
        have ⟨t'', qt''_l, qt''_r⟩ := @ih1 (abs u1') (Parallel.abs xs mem)
        cases qt''_l
        next w1 xs'' mem'' =>
        cases qt''_r
        case abs xs''' mem''' =>
          refine ⟨w1 ^ t', ?_, para_open_out xs''' mem''' qt'_r⟩
          apply Parallel.beta (free_union Var) <;> grind only [= Finset.mem_union, #c522]
