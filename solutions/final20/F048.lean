theorem dfsNode_dom (n : Nat) (f : Nat → Nat → Bool) :
    ∀ (fuel : Nat) (path : Array Nat) (invPath : Array UInt64) (p : Part) (st : St)
      (D : List (List UInt64) → Prop),
      Node n f path invPath p → n + 1 ≤ numCells n p + fuel → st.abortTo = none →
      StGood n f st → Pth st path → Jmp n f (DomD D st) path st →
        Guar n f D path st (dfsNode (Graph.ofOracle n f) fuel path invPath p st) := by
  refine dfsNode.induct (Graph.ofOracle n f)
    (motive1 := fun fuel path invPath p st => ∀ D : List (List UInt64) → Prop,
      Node n f path invPath p → n + 1 ≤ numCells n p + fuel → st.abortTo = none →
      StGood n f st → Pth st path → Jmp n f (DomD D st) path st →
        Guar n f D path st (dfsNode (Graph.ofOracle n f) fuel path invPath p st))
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
    exact absurd hfuel (by have := numCells_le (n := n) p; omega)
  case refine_2 =>
    intro path invPath p st fuel habort D _ _ hnone _ _ _
    rw [hnone] at habort; simp at habort
  case refine_3 =>
    intro path invPath p st fuel habort hprune D hnode _ hnone _ _ _
    simp only [dfsNode_pruned (by simpa only [Bool.not_eq_true] using habort) hprune]
    refine ⟨fun j hj => absurd (hnone.symm.trans hj) (by simp), fun k hk => ?_, BestMono.rfl st⟩
    rw [hnone] at hk; simp only [stopDepth] at hk
    exact Or.inl (pruneNode_none hprune ((ancReach_full hnode k).1 hk)).dom
  case refine_4 =>
    intro path invPath p st fuel habort st1 hprune htc D hnode hfuel hnone hgood hpth hjmp
    have hmono := dfsNode_mono n f (fuel + 1) path invPath p st hnode.wf hfuel
    simp only [dfsNode_leaf (by simpa only [Bool.not_eq_true] using habort) hprune htc] at hmono ⊢
    set st2 : St := { st1 with nodes := st1.nodes + 1 }
    have hrec2 : ∀ l, Rec st2 l → Rec st l := fun l hl => pruneNode_rec hprune hl
    have hgood2 : StGood n f st2 := (show StGood n f st1 from pruneNode_good hprune hgood)
    have hpth2 : Pth st2 path := fun l hl => hpth l (hrec2 l hl)
    have hjmp2 : Jmp n f (DomD D st) path st2 := fun l hl => hjmp l (hrec2 l hl)
    refine ⟨fun j hj => (leaf_abort_dom hnode hgood2 hpth2 hjmp2 hj).1, fun k hk => ?_, hmono⟩
    rcases hab : (leafUpdate (Graph.ofOracle n f) path invPath p.lab st2).abortTo with _ | j
    · rw [hab] at hk; simp only [stopDepth] at hk
      have hkk := reach_leaf_key htc ((ancReach_full hnode k).1 hk)
      exact Or.inl (hkk ▸ leafUpdate_dom_new (Graph.ofOracle n f) path invPath p.lab st2)
    · obtain ⟨hjlt, hdk⟩ := leaf_abort_dom hnode hgood2 hpth2 hjmp2 hab
      simp only [hab, stopDepth, Nat.min_eq_left (show j + 1 ≤ path.size by omega)] at hk
      exact (hdk k hk).up hmono
  case refine_5 =>
    intro path invPath p st fuel habort st1 hprune st2 s htc verts orb ih D hnode hfuel hnone
      hgood hpth hjmp
    have hp : Part.WF n p := hnode.wf
    have hmono := dfsNode_mono n f (fuel + 1) path invPath p st hp hfuel
    simp only [dfsNode_branch (by simpa only [Bool.not_eq_true] using habort) hprune htc] at hmono ⊢
    have hrec2 : ∀ l, Rec st2 l → Rec st l := fun l hl => pruneNode_rec hprune hl
    have hgood2 : StGood n f st2 := (show StGood n f st1 from pruneNode_good hprune hgood)
    have hpth2 : Pth st2 path := fun l hl => hpth l (hrec2 l hl)
    have hjmp2 : Jmp n f (DomD (DomD D st) st2) path st2 := by
      intro l hl j hj1 hj2 ht hne k hk
      exact (hjmp l (hrec2 l hl) j hj1 hj2 ht hne k hk).of
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
      (extract_nodup hp s p.cen[s]!) (by omega)
      (by rw [pruneNode_abortTo hprune]; exact hnone) hgood2
      (fun l hl w _ hw => hpth2 l hl hw.of_push) (JmpC.of_jmp hjmp2 hpth2) hC (by simp)
      markP_replicate hF
    exact ⟨h1, fun k hk => (h2 k hk).shift hmono, hmono⟩
  case refine_6 =>
    intro fuel path invPath p processed orb st D hnode htcex _ _ _ hnone _ _ _ hloop _ _ _
    obtain ⟨c, htc⟩ := htcex; simp only [dfsChildren_nil]
    refine ⟨fun j hj => absurd (hnone.symm.trans hj) (by simp), fun k hk => ?_, BestMono.rfl st⟩
    rw [hnone] at hk; simp only [stopDepth] at hk
    obtain ⟨w, hw, hsub⟩ := (reach_iff_subR htc k).1 ((ancReach_full hnode k).1 hk)
    exact (hloop w hw (by simp)).2 k hsub
  case refine_7 =>
    intro fuel path invPath p processed orb st v vs habort D _ _ _ _ _ hnone _ _ _ _ _ _ _
    rw [hnone] at habort; simp at habort
  all_goals
    intro fuel path invPath p processed orb st v vs habort orb1 hmark
    simp only [Bool.not_eq_true] at habort
  case refine_8 =>
    intro ih D hnode htcex hverts hnodup hfuel hnone hgood hpthc hjmpc hloop hproc hmarkP hgens
    have hgens1 : ∀ g ∈ orb1.gens,
        IsAutoArr n f g ∧ ∀ i, i < path.size → g[path[i]!]! = path[i]! :=
      orbRefresh_gens hgens hgood
    have hmarkP1 : MarkP (Dchild n f D invPath p st) orb1.mark :=
      orbRefresh_markP (fun g hg w hw =>
        dchild_gen hnode (hgood.2.2 g (mem_usableAutos hg).1) (mem_usableAutos hg).2 w hw)
        hproc hmarkP
    simp only [dfsChildren_marked habort hmark]
    refine ih D hnode htcex (fun w hw => hverts w (List.mem_cons_of_mem _ hw)) hnodup.of_cons
      hfuel hnone hgood (fun l hl w hw => hpthc l hl w (List.mem_cons_of_mem _ hw)) hjmpc
      ?_ hproc hmarkP1 hgens1
    intro w hw hnw; by_cases hwv : w = v
    · subst hwv; exact hmarkP1 w hmark
    · exact hloop w hw (by simp [hwv, hnw])
  case' refine_9 =>
    intro p' s hind inW p'' tr href childInv' st1 st2 habort2
      ih1 D hnode htcex hverts hnodup hfuel hnone hgood hpthc hjmpc hloop hproc hmarkP hgens
  case' refine_10 =>
    intro p' s hind inW p'' tr href childInv' st1 st2 habort2
      orb2 ih1 _ih1' ih2 D hnode htcex hverts hnodup hfuel hnone hgood hpthc hjmpc
      hloop hproc hmarkP hgens
  all_goals
    simp only [Bool.not_eq_true] at hmark
    obtain ⟨c, htc, hv, hcell⟩ := hverts v (by simp)
    have hchild : child (Graph.ofOracle n f) p v = (p'', tr) := by rw [child, hind]; exact href
    have hnode' : Node n f (path.push v) childInv' p'' := by
      simpa only [childInv, hchild] using (Node.step hnode htc hv hcell)
    have hnc : numCells n p < numCells n p'' := by
      simpa only [hchild] using (numCells_child (n := n) (f := f) hnode.wf htc hv hcell)
  case refine_9 =>
    simp only [dfsChildren_step_stop habort hmark hind href habort2]
    exact guar_stop (ih1 D hnode' (by omega) hnone hgood
      (fun l hl => hpthc l hl v (by simp)) (hjmpc.child v)) habort2
  case refine_10 =>
    simp only [Bool.not_eq_true] at habort2
    simp only [dfsChildren_step_go habort hmark hind href habort2]
    have hg1 := ih1 D hnode' (by omega) hnone hgood
      (fun l hl => hpthc l hl v (by simp)) (hjmpc.child v)
    obtain ⟨hdv, hab2, hm2⟩ := guar_go hnode hv hg1 habort2
    set ST2 : St :=
      unwind path (dfsNode (Graph.ofOracle n f) fuel (path.push v) childInv' p'' st)
    have hvne : ∀ w ∈ vs, ¬ w = v := fun w hw he => (List.nodup_cons.1 hnodup).1 (he ▸ hw)
    have hgood2 : StGood n f ST2 :=
      (dfsNode_good n f fuel (path.push v) childInv' p'' st hnode' hgood).unwind path
    have hrec2 := rec_iff_stq.1 ((dfsNode_paths n f
        (fun Q => PathPre (path.push v) Q ∨ ∃ z, Rec st z ∧ z.path = Q)
        fuel (path.push v) childInv' p'' st (fun Q hQ => Or.inl hQ)
        (rec_iff_stq.2 (fun z hz => Or.inr ⟨z, hz, rfl⟩))).unwind path)
    have hgens1 : ∀ g ∈ orb1.gens,
        IsAutoArr n f g ∧ ∀ i, i < path.size → g[path[i]!]! = path[i]! :=
      orbRefresh_gens hgens hgood
    have hmarkP1 : MarkP (Dchild n f D invPath p st) orb1.mark :=
      orbRefresh_markP (fun g hg w hw =>
        dchild_gen hnode (hgood.2.2 g (mem_usableAutos hg).1) (mem_usableAutos hg).2 w hw)
        hproc hmarkP
    have hA : ∀ l, Rec ST2 l → ∀ w ∈ vs, ¬ PathPre (path.push w) l.path := by
      intro l hl w hw hpre; rcases hrec2 l hl with hp1 | ⟨z, hz, hzp⟩
      · exact hvne w hw ((PathPre.push_iff.1 hpre).2.2.symm.trans (PathPre.push_iff.1 hp1).2.2)
      · exact hpthc z hz w (List.mem_cons_of_mem _ hw) (by rw [hzp]; exact hpre)
    have hB : JmpC n f (DomD D ST2) path ST2 := by
      intro l hl j hjle hjl htake hne k hk; rcases hrec2 l hl with hp1 | ⟨z, hz, hzp⟩
      · rcases Nat.lt_or_ge j path.size with hlt | hge
        · exact absurd ((PathPre.push_iff.1 hp1).1.2 j hlt) (hne hlt)
        · obtain rfl : j = path.size := by omega
          have hcong : (path.push v).toList.take (path.size + 1)
              = l.path.toList.take (path.size + 1) := by
            simpa using take_of_pathPre hp1
          exact hdv.2 k ((ancReach_child hnode v k).1 ((ancReach_congr hcong k).2 hk))
      · simp only [← hzp] at hjl htake hne hk
        exact (hjmpc z hz j hjle hjl htake hne k hk).up hm2
    have hC : ∀ w, Chld n p w → w ∉ vs → Dchild n f D invPath p ST2 w := by
      intro w hw hnw; by_cases hwv : w = v
      · subst hwv; exact hdv
      · exact (hloop w hw (by simp [hwv, hnw])).up hm2
    have hE : ∀ w ∈ processed.push v, Dchild n f D invPath p ST2 w := by
      intro w hw; rcases Array.mem_push.1 hw with hw1 | rfl
      · exact (hproc w hw1).up hm2
      · exact hdv
    have hF : MarkP (Dchild n f D invPath p ST2) orb2.mark := by
      refine closureLoop_P (fun g hg w hw =>
          dchild_gen hnode (hgens1 g hg).1 (hgens1 g hg).2 w hw) _ _ _
        (markP_set (fun w hw => (hmarkP1 w hw).up hm2) hdv) (fun i hi => ?_)
      obtain rfl : i = 0 := by
        have h1 : (#[v] : Array Nat).size = 1 := rfl; omega
      simpa using hdv
    obtain ⟨h1, h2, h3⟩ := ih2 D hnode htcex
      (fun w hw => hverts w (List.mem_cons_of_mem _ hw)) hnodup.of_cons hfuel hab2 hgood2
      hA hB hC hE hF hgens1
    exact ⟨h1, h2, hm2.trans h3⟩
