theorem parallel_diamond : Diamond ((· ⭢ₚ ·) : Term Var → Term Var → Prop) := by
  have join {m l r : Term Var} {xs ys : Finset Var}
      (ih : ∀ x ∉ xs, ∀ {v}, (m ^ fvar x) ⭢ₚ v →
        ∃ w, (l ^ fvar x) ⭢ₚ w ∧ v ⭢ₚ w)
      (hr : ∀ x ∉ ys, (m ^ fvar x) ⭢ₚ r ^ fvar x) :
      ∃ w, abs l ⭢ₚ w ∧ abs r ⭢ₚ w := by
    have ⟨x, qx⟩ := fresh_exists $ xs ∪ ys ∪ fv l ∪ fv r
    simp only [Finset.mem_union, not_or] at qx
    have ⟨w, hw⟩ := ih x qx.1.1.1 (hr x qx.1.1.2)
    suffices ∀ {v}, x ∉ fv v → (v ^ fvar x) ⭢ₚ w →
        abs v ⭢ₚ abs (w ^* x) from
      ⟨_, this qx.1.2 hw.1, this qx.2 hw.2⟩
    clear ih hr hw qx
    intro v hv h
    apply Parallel.abs ∅
    intro y _
    have := para_open_close x y 0 h
    grind
  intros t t1 t2 tpt1
  induction tpt1 generalizing t2 <;> intro tpt2
  case fvar x =>
    cases tpt2
    exact ⟨_, Parallel.fvar x, Parallel.fvar x⟩
  case abs =>
    rename_i ih
    cases tpt2
    rename_i mem'
    exact join ih mem'
  case beta =>
    rename_i ih1 ih2
    cases tpt2
    case' app =>
      rename_i s1pu2 s2pu2'
      cases s1pu2
      rename_i mem'
    case' beta =>
      rename_i mem' s2pu2'
    all_goals
      obtain ⟨w, hl, hr⟩ := join ih1 mem'
      obtain ⟨v, hv1, hv2⟩ := ih2 s2pu2'
      cases hl
      cases hr
      rename_i ys hys zs hzs
      exact ⟨_, para_open_out ys hys hv1, by
        first
        | exact Parallel.beta zs hzs hv2
        | exact para_open_out zs hzs hv2⟩
  case app =>
    rename_i s1ps1' _ ih1 ih2
    cases tpt2
    case app =>
      rename_i s1 s2
      obtain ⟨l, hl, hl'⟩ := ih1 s1
      obtain ⟨r, hr, hr'⟩ := ih2 s2
      exact ⟨_, Parallel.app hl hr, Parallel.app hl' hr'⟩
    case beta =>
      rename_i xs mem s2pu2'
      cases s1ps1'
      obtain ⟨t', qt'_l, qt'_r⟩ := ih2 s2pu2'
      obtain ⟨t'', qt''_l, qt''_r⟩ := ih1 (Parallel.abs xs mem)
      cases qt''_l
      cases qt''_r
      rename_i xs'' mem'' xs''' mem'''
      exact ⟨_, Parallel.beta xs'' mem'' qt'_l,
        para_open_out xs''' mem''' qt'_r⟩
