theorem dfsNode_dom (n : Nat) (f : Nat → Nat → Bool) :
    ∀ (fuel : Nat) (path : Array Nat) (invPath : Array UInt64) (p : Part) (st : St)
      (D : List (List UInt64) → Prop),
      Node n f path invPath p → n + 1 ≤ numCells n p + fuel → st.abortTo = none →
      StGood n f st → Pth st path → Jmp n f (DomD D st) path st →
        Guar n f D path st (dfsNode (Graph.ofOracle n f) fuel path invPath p st) := by
  refine dfsNode.induct (Graph.ofOracle n f)
    (motive1 := _)
    (motive2 := fun fuel path invPath p verts processed orb st =>
      ∀ D : List (List UInt64) → Prop,
      Node n f path invPath p → (∃ c, p.targetCell n = some c) → (∀ v ∈ verts, Chld n p v) →
      verts.Nodup → n ≤ numCells n p + fuel → st.abortTo = none → StGood n f st →
      (∀ l, Rec st l → ∀ w ∈ verts, ¬ PathPre (path.push w) l.path) →
      JmpC n f (DomD D st) path st →
      (∀ w, Chld n p w → w ∉ verts → Dchild n f D invPath p st w) →
      (∀ w ∈ processed, Dchild n f D invPath p st w) →
      MarkP (Dchild n f D invPath p st) orb.mark →
      (∀ g ∈ orb.gens, IsAutoArr n f g ∧ ∀ i, i < path.size → g[path[i]!]! = path[i]!) →
        Guar n f D path st
          (dfsChildren (Graph.ofOracle n f) fuel path invPath p verts processed orb st))
    ?_ ?_ ?_ ?_ ?_ ?_ ?_ ?_ ?_ ?_
  case refine_1 =>
    intro path invPath p st D hnode hfuel _ _ _ _
    exact False.elim (Nat.not_succ_le_self n (hfuel.trans (numCells_le (n := n) p)))
  case refine_2 =>
    intro path invPath p st fuel habort D _ _ hnone _ _ _
    rw [hnone] at habort; simp at habort
  case refine_3 =>
    intro path invPath p st fuel habort hprune D hnode _ hnone _ _ _
    rw [dfsNode_pruned (by simpa using habort) hprune]
    refine ⟨fun j hj => absurd (hnone.symm.trans hj) (by simp), fun k hk => ?_, BestMono.rfl st⟩
    rw [hnone] at hk; simp only [stopDepth] at hk
    exact Or.inl (pruneNode_none hprune ((ancReach_full hnode k).1 hk)).dom
  case' refine_4 =>
    intro path invPath p st fuel habort st1 hprune htc D hnode hfuel hnone hgood hpth hjmp
  case' refine_5 =>
    intro path invPath p st fuel habort st1 hprune st2 s htc verts orb ih D hnode hfuel hnone
      hgood hpth hjmp
  case' refine_4 | refine_5 =>
    have hmono := dfsNode_mono n f (fuel + 1) path invPath p st hnode.wf hfuel
  case' refine_4 =>
    rw [dfsNode_leaf (by simpa using habort) hprune htc] at hmono ⊢
    set st2 : St := { st1 with nodes := st1.nodes + 1 }
  case' refine_5 =>
    rw [dfsNode_branch (by simpa using habort) hprune htc] at hmono ⊢
  case' refine_4 | refine_5 =>
    have hrec2 : ∀ l, Rec st2 l → Rec st l := fun l hl => pruneNode_rec hprune hl
    have hgood2 : StGood n f st2 := (show StGood n f st1 from pruneNode_good hprune hgood)
    have hpth2 : Pth st2 path := fun l hl => hpth l (hrec2 l hl)
  case refine_4 =>
    have hjmp2 : Jmp n f (DomD D st) path st2 := fun l hl => hjmp l (hrec2 l hl)
    refine ⟨fun j hj => (leaf_abort_dom hnode hgood2 hpth2 hjmp2 hj).1, fun k hk => ?_, hmono⟩
    rcases hab : (leafUpdate (Graph.ofOracle n f) path invPath p.lab st2).abortTo with _ | j
    · rw [hab] at hk; simp only [stopDepth] at hk
      have hkk := reach_leaf_key htc ((ancReach_full hnode k).1 hk)
      exact Or.inl (hkk ▸ leafUpdate_dom_new (Graph.ofOracle n f) path invPath p.lab st2)
    · obtain ⟨hjlt, hdk⟩ := leaf_abort_dom hnode hgood2 hpth2 hjmp2 hab
      simp only [hab, stopDepth, Nat.min_eq_left hjlt] at hk
      exact (hdk k hk).up hmono
  case refine_5 =>
    have hp : Part.WF n p := hnode.wf
    obtain ⟨h1, h2, h3⟩ := ih (DomD D st) hnode ⟨s, htc⟩
      (fun w hw => ⟨s, htc, mem_extract_lt hp hw,
        mem_extract_cell hp (targetCell_lt n p s htc) (targetCell_cst hp htc) hw⟩)
      (extract_nodup hp s p.cen[s]!) (Nat.le_of_succ_le_succ hfuel)
      (by rw [pruneNode_abortTo hprune]; exact hnone) hgood2
      (fun l hl w _ hw => hpth2 l hl hw.of_push)
      (JmpC.of_jmp (fun l hl j hj1 hj2 ht hne k hk =>
        (hjmp l (hrec2 l hl) j hj1 hj2 ht hne k hk).of) hpth2)
      (by
        intro w hw hnw; obtain ⟨c, hc, hwn, hcell⟩ := hw
        rw [(Option.some.inj (htc.symm.trans hc)).symm] at hcell
        exact absurd (mem_extract_cell' hp (targetCell_lt n p s htc) (targetCell_cst hp htc)
          hwn hcell) hnw)
      (by simp) markP_replicate
      (by
        intro g hg; obtain ⟨hg1, hg2⟩ := mem_usableAutos hg
        exact ⟨hgood2.2.2 g hg1, hg2⟩)
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
  case' refine_8 =>
    intro fuel path invPath p processed orb st v vs habort orb1 hmark ih D hnode htcex hverts
      hnodup hfuel hnone hgood hpthc hjmpc hloop hproc hmarkP hgens
  case' refine_9 =>
    intro fuel path invPath p processed orb st v vs habort orb1 hmark p' s hind inW p'' tr href
      childInv' st1 st2 habort2 ih1 D hnode htcex hverts hnodup hfuel hnone hgood hpthc hjmpc
      hloop hproc hmarkP hgens
  case' refine_10 =>
    intro fuel path invPath p processed orb st v vs habort orb1 hmark p' s hind inW p'' tr href
      childInv' st1 st2 habort2 orb2 ih1 _ih1' ih2 D hnode htcex hverts hnodup hfuel hnone
      hgood hpthc hjmpc hloop hproc hmarkP hgens
  case' refine_8 | refine_10 =>
    have hgens1 := orbRefresh_gens (processed := processed) hgens hgood
    have hmarkP1 : MarkP (Dchild n f D invPath p st) orb1.mark :=
      orbRefresh_markP (fun g hg w hw =>
        dchild_gen hnode (hgood.2.2 g (mem_usableAutos hg).1) (mem_usableAutos hg).2 w hw)
        hproc hmarkP
  case refine_8 =>
    rw [dfsChildren_marked (by simpa using habort) hmark]
    refine ih D hnode htcex (fun w hw => hverts w (List.mem_cons_of_mem _ hw)) hnodup.of_cons
      hfuel hnone hgood (fun l hl w hw => hpthc l hl w (List.mem_cons_of_mem _ hw)) hjmpc
      ?_ hproc hmarkP1 hgens1
    intro w hw hnw; by_cases hwv : w = v
    · subst hwv; exact hmarkP1 w hmark
    · exact hloop w hw (by simp [hwv, hnw])
  all_goals
    obtain ⟨c, htc, hv, hcell⟩ := hverts v (by simp)
    have hchild : child (Graph.ofOracle n f) p v = (p'', tr) := by rw [child, hind]; exact href
    have hcinv : childInv (Graph.ofOracle n f) invPath p v = childInv' := by rw [childInv, hchild]
    have hnode' : Node n f (path.push v) childInv' p'' := by
      simpa only [hchild, hcinv] using Node.step hnode htc hv hcell
    have hnc : numCells n p < numCells n p'' := by
      simpa only [hchild] using numCells_child (n := n) (f := f) hnode.wf htc hv hcell
    have hg1 := ih1 D hnode'
      (Nat.le_trans (Nat.succ_le_succ hfuel) (by
        simpa only [Nat.succ_add] using Nat.add_le_add_right hnc fuel)) hnone hgood
      (fun l hl => hpthc l hl v (by simp)) (hjmpc.child v)
  case refine_9 =>
    rw [dfsChildren_step_stop (by simpa using habort)
      (by simp only [Bool.not_eq_true] at hmark; exact hmark) hind href habort2]
    exact guar_stop hg1 habort2
  case refine_10 =>
    rw [dfsChildren_step_go (by simpa using habort)
      (by simp only [Bool.not_eq_true] at hmark; exact hmark) hind href
      (by simp only [Bool.not_eq_true] at habort2; exact habort2)]
    obtain ⟨hdv, hab2, hm2⟩ := guar_go hnode hv hg1
      (by simp only [Bool.not_eq_true] at habort2; exact habort2)
    let ST2 := unwind path (dfsNode (Graph.ofOracle n f) fuel (path.push v) childInv' p'' st)
    have hvne : ∀ w ∈ vs, ¬ w = v := fun w hw he => (List.nodup_cons.1 hnodup).1 (he ▸ hw)
    have hgood2 :=
      (dfsNode_good n f fuel (path.push v) childInv' p'' st hnode' hgood).unwind path
    have hrec2 := rec_iff_stq.1 ((dfsNode_paths n f
        (fun Q => PathPre (path.push v) Q ∨ ∃ z, Rec st z ∧ z.path = Q)
        fuel (path.push v) childInv' p'' st (fun Q hQ => Or.inl hQ)
        (rec_iff_stq.2 (fun z hz => Or.inr ⟨z, hz, rfl⟩))).unwind path)
    have hF : MarkP (Dchild n f (DomD D ST2) invPath p ST2) orb2.mark := by
      refine closureLoop_P (fun g hg w hw =>
          dchild_gen hnode (hgens1 g hg).1 (hgens1 g hg).2 w hw) _ _ _
        (markP_set (fun w hw => ((hmarkP1 w hw).up hm2).self_of) hdv.self_of) (fun i hi => ?_)
      obtain rfl : i = 0 := Nat.eq_zero_of_le_zero (Nat.le_of_lt_succ hi)
      simpa using hdv.self_of
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
                = l.path.toList.take (path.size + 1) := by simpa using take_of_pathPre hp1
            exact Or.inr (hdv.2 k ((ancReach_child hnode v k).1 ((ancReach_congr hcong k).2 hk)))
        · have hzjmp := hjmpc z hz
          rw [hzp] at hzjmp
          exact Or.inr ((hzjmp j hjle hjl htake hne k hk).up hm2))
      (by
        intro w hw hnw; by_cases hwv : w = v
        · subst hwv; exact hdv.self_of
        · exact ((hloop w hw (by simp [hwv, hnw])).up hm2).self_of)
      (by
        intro w hw; rcases Array.mem_push.1 hw with hw1 | rfl
        · exact ((hproc w hw1).up hm2).self_of
        · exact hdv.self_of)
      hF hgens1
    exact ⟨h1, fun k hk => (h2 k hk).shift h3, hm2.trans h3⟩
