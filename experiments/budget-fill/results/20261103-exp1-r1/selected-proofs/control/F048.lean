theorem dfsNode_dom (n : Nat) (f : Nat → Nat → Bool) :
    ∀ (fuel : Nat) (path : Array Nat) (invPath : Array UInt64) (p : Part) (st : St)
      (D : List (List UInt64) → Prop),
      Node n f path invPath p → n + 1 ≤ numCells n p + fuel → st.abortTo = none →
      StGood n f st → Pth st path → Jmp n f (DomD D st) path st →
        Guar n f D path st (dfsNode (Graph.ofOracle n f) fuel path invPath p st) := by
  let G := Graph.ofOracle n f
  refine dfsNode.induct G
    (motive1 := fun fuel path invPath p st => ∀ D,
      Node n f path invPath p → n + 1 ≤ numCells n p + fuel → st.abortTo = none →
      StGood n f st → Pth st path → Jmp n f (DomD D st) path st →
        Guar n f D path st (dfsNode G fuel path invPath p st))
    (motive2 := fun fuel path invPath p verts processed orb st =>
      ∀ D,
      Node n f path invPath p → (∃ c, p.targetCell n = some c) → (∀ v ∈ verts, Chld n p v) →
      verts.Nodup → n ≤ numCells n p + fuel → st.abortTo = none → StGood n f st →
      (∀ l, Rec st l → ∀ w ∈ verts, ¬ PathPre (path.push w) l.path) →
      JmpC n f (DomD D st) path st →
      (∀ w, Chld n p w → w ∉ verts → Dchild n f D invPath p st w) →
      (∀ w ∈ processed, Dchild n f D invPath p st w) →
      MarkP (Dchild n f D invPath p st) orb.mark →
      (∀ g ∈ orb.gens, IsAutoArr n f g ∧ ∀ i, i < path.size → g[path[i]!]! = path[i]!) →
        Guar n f D path st (dfsChildren G fuel path invPath p verts processed orb st))
    ?_ ?_ ?_ ?_ ?_ ?_ ?_ ?_ ?_ ?_
  case refine_1 =>
    intro path invPath p st D hnode hfuel _ _ _ _
    exact False.elim (Nat.not_succ_le_self n (hfuel.trans (numCells_le (n := n) p)))
  case refine_2 =>
    intro path invPath p st fuel habort D _ _ hnone _ _ _
    rw [hnone] at habort; simp at habort
  case refine_3 =>
    intro path invPath p st fuel habort hprune D hnode _ hnone _ _ _
    rw [dfsNode_pruned (Bool.eq_false_iff.mpr habort) hprune]
    refine ⟨fun j hj => absurd (hnone.symm.trans hj) (by simp), fun k hk => ?_, BestMono.rfl st⟩
    rw [hnone] at hk; simp only [stopDepth] at hk
    exact Or.inl (pruneNode_none hprune ((ancReach_full hnode k).1 hk)).dom
  case refine_4 =>
    intro path invPath p st fuel habort st1 hprune htc D hnode hfuel hnone hgood hpth hjmp
    have hmono := dfsNode_mono n f (fuel + 1) path invPath p st hnode.wf hfuel
    rw [dfsNode_leaf (Bool.eq_false_iff.mpr habort) hprune htc] at hmono ⊢
    set st2 : St := { st1 with nodes := st1.nodes + 1 }
    have hgood2 : StGood n f st2 := (show StGood n f st1 from pruneNode_good hprune hgood)
    have hpth2 : Pth st2 path := fun l hl => hpth l (pruneNode_rec hprune hl)
    have hjmp2 : Jmp n f (DomD D st) path st2 := fun l hl => hjmp l (pruneNode_rec hprune hl)
    refine ⟨fun j hj => (leaf_abort_dom hnode hgood2 hpth2 hjmp2 hj).1, fun k hk => ?_, hmono⟩
    rcases hab : (leafUpdate G path invPath p.lab st2).abortTo with _ | j
    · rw [hab] at hk; simp only [stopDepth] at hk
      have hkk := reach_leaf_key htc ((ancReach_full hnode k).1 hk)
      exact Or.inl (hkk ▸ leafUpdate_dom_new G path invPath p.lab st2)
    · obtain ⟨hjlt, hdk⟩ := leaf_abort_dom hnode hgood2 hpth2 hjmp2 hab
      simp only [hab, stopDepth, Nat.min_eq_left hjlt] at hk
      exact (hdk k hk).up hmono
  case refine_5 =>
    intro path invPath p st fuel habort st1 hprune st2 s htc verts orb ih D hnode hfuel hnone
      hgood hpth hjmp
    have hp := hnode.wf
    have hmono := dfsNode_mono n f (fuel + 1) path invPath p st hp hfuel
    rw [dfsNode_branch (Bool.eq_false_iff.mpr habort) hprune htc] at hmono ⊢
    have hgood2 : StGood n f st2 := (show StGood n f st1 from pruneNode_good hprune hgood)
    have hpth2 : Pth st2 path := fun l hl => hpth l (pruneNode_rec hprune hl)
    have hjmp2 : Jmp n f (DomD (DomD D st) st2) path st2 := by
      intro l hl j hj1 hj2 ht hne k hk
      exact (hjmp l (pruneNode_rec hprune hl) j hj1 hj2 ht hne k hk).of
    have hC : ∀ w, Chld n p w → w ∉ verts → Dchild n f (DomD D st) invPath p st2 w := by
      intro w hw hnw; obtain ⟨c, hc, hwn, hcell⟩ := hw
      rw [(Option.some.inj (htc.symm.trans hc)).symm] at hcell
      exact absurd (mem_extract_cell' hp (targetCell_lt n p s htc) (targetCell_cst hp htc)
        hwn hcell) hnw
    have hF : ∀ g ∈ orb.gens,
        IsAutoArr n f g ∧ ∀ i, i < path.size → g[path[i]!]! = path[i]! := by
      intro g hg; obtain ⟨hg1, hg2⟩ := mem_usableAutos hg
      exact ⟨hgood2.2.2 g hg1, hg2⟩
    obtain ⟨h1, h2, h3⟩ := ih (DomD D st) hnode ⟨s, htc⟩
      (fun w hw => ⟨s, htc, mem_extract_lt hp hw,
        mem_extract_cell hp (targetCell_lt n p s htc) (targetCell_cst hp htc) hw⟩)
      (extract_nodup hp s p.cen[s]!) (Nat.le_of_succ_le_succ hfuel)
      (by rw [pruneNode_abortTo hprune]; exact hnone) hgood2
      (fun l hl w _ hw => hpth2 l hl hw.of_push) (JmpC.of_jmp hjmp2 hpth2) hC (by simp)
      markP_replicate hF
    exact ⟨h1, fun k hk => (h2 k hk).shift hmono, hmono⟩
  case refine_6 =>
    intro fuel path invPath p processed orb st D hnode htcex _ _ _ hnone _ _ _ hloop _ _ _
    obtain ⟨c, htc⟩ := htcex; rw [dfsChildren_nil]
    refine ⟨fun j hj => absurd (hnone.symm.trans hj) (by simp), fun k hk => ?_, BestMono.rfl st⟩
    rw [hnone] at hk; simp only [stopDepth] at hk
    obtain ⟨w, hw, hsub⟩ := (reach_iff_subR htc k).1 ((ancReach_full hnode k).1 hk)
    exact (hloop w hw (by simp)).2 k hsub
  case refine_7 =>
    intro fuel path invPath p processed orb st v vs habort D _ _ _ _ _ hnone _ _ _ _ _ _ _
    rw [hnone] at habort; simp at habort
  all_goals
    intro fuel path invPath p processed orb st v vs habort orb1 hmark
  case' refine_8 => intro ih
  case' refine_9 =>
    intro p' s hind inW p'' tr href childInv' st1 st2 habort2 ih1
  case' refine_10 =>
    intro p' s hind inW p'' tr href childInv' st1 st2 habort2 orb2 ih1 _ih1' ih2
  all_goals
    intro D hnode htcex hverts hnodup hfuel hnone hgood hpthc hjmpc hloop hproc hmarkP hgens
    have hgens1 := orbRefresh_gens (processed := processed) hgens hgood
    have hmarkP1 : MarkP (Dchild n f D invPath p st) orb1.mark :=
      orbRefresh_markP (fun g hg w hw =>
        dchild_gen hnode (hgood.2.2 g (mem_usableAutos hg).1) (mem_usableAutos hg).2 w hw)
        hproc hmarkP
  case refine_8 =>
    rw [dfsChildren_marked (Bool.eq_false_iff.mpr habort) hmark]
    refine ih D hnode htcex (fun w hw => hverts w (List.mem_cons_of_mem _ hw)) hnodup.of_cons
      hfuel hnone hgood (fun l hl w hw => hpthc l hl w (List.mem_cons_of_mem _ hw)) hjmpc
      ?_ hproc hmarkP1 hgens1
    intro w hw hnw; by_cases hwv : w = v
    · subst hwv; exact hmarkP1 w hmark
    · exact hloop w hw (by simp [hwv, hnw])
  all_goals
    have hmark0 := Bool.eq_false_iff.mpr hmark
    obtain ⟨c, htc, hv, hcell⟩ := hverts v (by simp)
    have hchild : child (Graph.ofOracle n f) p v = (p'', tr) := by rw [child, hind]; exact href
    have hnode' : Node n f (path.push v) childInv' p'' := by
      simpa only [childInv, hchild] using Node.step hnode htc hv hcell
    have hnc : numCells n p < numCells n p'' := by
      have := numCells_child (n := n) (f := f) hnode.wf htc hv hcell
      rwa [hchild] at this
    have hfuel' := Nat.succ_le_of_lt (lt_of_le_of_lt hfuel (Nat.add_lt_add_right hnc fuel))
  case refine_9 =>
    rw [dfsChildren_step_stop (Bool.eq_false_iff.mpr habort) hmark0 hind href habort2]
    exact guar_stop (ih1 D hnode' hfuel' hnone hgood
      (fun l hl => hpthc l hl v (by simp)) (hjmpc.child v)) habort2
  case refine_10 =>
    have habort0 := Bool.eq_false_iff.mpr habort2
    rw [dfsChildren_step_go (Bool.eq_false_iff.mpr habort) hmark0 hind href habort0]
    have hg1 := ih1 D hnode' hfuel' hnone hgood
      (fun l hl => hpthc l hl v (by simp)) (hjmpc.child v)
    obtain ⟨hdv, hab2, hm2⟩ := guar_go hnode hv hg1 habort0
    set ST2 : St := unwind path (dfsNode G fuel (path.push v) childInv' p'' st)
    have hvne : ∀ w ∈ vs, ¬ w = v := fun w hw he => (List.nodup_cons.1 hnodup).1 (he ▸ hw)
    have hgood2 : StGood n f ST2 :=
      (dfsNode_good n f fuel (path.push v) childInv' p'' st hnode' hgood).unwind path
    have hrec2 := rec_iff_stq.1 ((dfsNode_paths n f
        (fun Q => PathPre (path.push v) Q ∨ ∃ z, Rec st z ∧ z.path = Q)
        fuel (path.push v) childInv' p'' st (fun Q hQ => Or.inl hQ)
        (rec_iff_stq.2 (fun z hz => Or.inr ⟨z, hz, rfl⟩))).unwind path)
    obtain ⟨h1, h2, h3⟩ := ih2 (DomD D ST2) hnode htcex
      (fun w hw => hverts w (List.mem_cons_of_mem _ hw)) hnodup.of_cons hfuel hab2 hgood2
      (by
        intro l hl w hw hpre; rcases hrec2 l hl with hp1 | ⟨z, hz, hzp⟩
        · exact hvne w hw ((PathPre.push_iff.1 hpre).2.2.symm.trans (PathPre.push_iff.1 hp1).2.2)
        · exact hpthc z hz w (List.mem_cons_of_mem _ hw) (by rw [hzp]; exact hpre))
      (by
        intro l hl j hjle hjl htake hne k hk; rcases hrec2 l hl with hp1 | ⟨z, hz, hzp⟩
        · rcases Nat.lt_or_ge j path.size with hlt | hge
          · exact absurd ((PathPre.push_iff.1 hp1).1.2 j hlt) (hne hlt)
          · obtain rfl : j = path.size := Nat.le_antisymm hjle hge
            have hcong : (path.push v).toList.take (path.size + 1)
                = l.path.toList.take (path.size + 1) := by
              simpa using take_of_pathPre hp1
            exact Or.inr (hdv.2 k ((ancReach_child hnode v k).1 ((ancReach_congr hcong k).2 hk)))
        · rw [← hzp] at hjl htake hne hk
          exact Or.inr ((hjmpc z hz j hjle hjl htake hne k hk).up hm2))
      (by
        intro w hw hnw; by_cases hwv : w = v
        · subst hwv; exact hdv.self_of
        · exact ((hloop w hw (by simp [hwv, hnw])).up hm2).self_of)
      (by
        intro w hw; rcases Array.mem_push.1 hw with hw1 | rfl
        · exact ((hproc w hw1).up hm2).self_of
        · exact hdv.self_of)
      (by
        refine closureLoop_P (fun g hg w hw =>
            dchild_gen hnode (hgens1 g hg).1 (hgens1 g hg).2 w hw) _ _ _
          (markP_set (fun w hw => ((hmarkP1 w hw).up hm2).self_of) hdv.self_of) (fun i hi => ?_)
        obtain rfl : i = 0 := Nat.le_antisymm (Nat.le_of_lt_succ hi) (Nat.zero_le i)
        exact hdv.self_of) hgens1
    exact ⟨h1, fun k hk => (h2 k hk).shift h3, hm2.trans h3⟩
