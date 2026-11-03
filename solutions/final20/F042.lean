theorem matsumoto_reduced_aux [MatsumotoCondition cs] (p : ℕ) (l l' : List B)
(len_l_eq_p : l.length = p) (len_l'_eq_p : l'.length = p)
(l_reduced : cs.IsReduced l) (l'_reduced : cs.IsReduced l') (h_eq : π l = π l') :
  ∃ bms : List (cs.BraidMove), cs.applyBraidMoveSequence bms l = l' := by
  induction p generalizing l l' with
  | zero =>
    obtain rfl := List.length_eq_zero_iff.mp len_l_eq_p
    obtain rfl := List.length_eq_zero_iff.mp len_l'_eq_p
    exact ⟨[], rfl⟩
  | succ p ih =>
    have link {a : B} {x y : List B}
        (hx : cs.IsReduced (a :: x)) (hy : cs.IsReduced (a :: y))
        (he : π (a :: x) = π (a :: y))
        (hl : x.length = p ∨ y.length = p) :
        ∃ bms, cs.applyBraidMoveSequence bms (a :: x) = a :: y := by
      have hxy := Nat.succ.inj (cs.eq_length_of_isReduced (a :: x) (a :: y) he hx hy)
      have hxlen : x.length = p := hl.elim id (fun h => hxy.trans h)
      exact cs.matsumoto_reduced_inductionStep_of_firstLetterEq p x y a
        hxlen (hxy.symm.trans hxlen) he hx hy ih
    rcases cons_of_length_succ l len_l_eq_p with ⟨i, x, rfl, hxlen⟩
    rcases cons_of_length_succ l' len_l'_eq_p with ⟨j, y, rfl, hylen⟩
    by_cases hij : i = j
    · subst j
      exact cs.matsumoto_reduced_inductionStep_of_firstLetterEq p x y i
        hxlen hylen h_eq l_reduced l'_reduced ih
    · have bridge {u v a b : List B} :
          π (i :: x) = π u → π u = π v →
          cs.IsReduced u → cs.IsReduced v →
          (∃ bms, cs.applyBraidMoveSequence bms u = v) →
          u = i :: a → v = j :: b →
          ∃ bms, cs.applyBraidMoveSequence bms (i :: x) = j :: y := by
        rintro hu hs hru hrv hmv rfl rfl
        exact cs.concatenate_braidMove_sequences _ _ _
          (link l_reduced hru hu (Or.inl hxlen))
          (cs.concatenate_braidMove_sequences _ _ _ hmv
            (link hrv l'_reduced (hs.symm.trans (hu.symm.trans h_eq)) (Or.inr hylen)))
      obtain ⟨m, hm⟩ : ∃ m : ℕ, M i j = m + 1 :=
        ⟨M i j - 1, (Nat.sub_add_cancel (MatsumotoCondition.one_le_M cs i j)).symm⟩
      obtain ⟨t, hu, hru⟩ := cs.prefix_braidWord x y i j hij h_eq l_reduced l'_reduced
      have hs : π (braidWord M i j ++ t) = π (braidWord M j i ++ t) := by
        rw [wordProd_append, wordProd_append, cs.wordProd_braidWord_eq i j]
      have hrv : cs.IsReduced (braidWord M j i ++ t) :=
        cs.isReduced_of_eq_length _ _
          (by simp only [List.length_append, length_alternatingWord]; rw [M.symmetric]) hs hru
      have move (a b : B) : ∃ bms, cs.applyBraidMoveSequence bms
          (braidWord M a b ++ t) = braidWord M b a ++ t := by
        refine ⟨[BraidMove.mk a b 0], ?_⟩
        change cs.applyBraidMove (BraidMove.mk a b 0) (braidWord M a b ++ t) = _
        rw [applyBraidMove, ← length_alternatingWord a b (M a b),
          List.take_left, if_pos rfl, List.drop_left]
      by_cases he : Even m
      · exact bridge (hu.trans hs) hs.symm hrv hru (move j i)
          (by rw [braidWord, M.symmetric j i, hm, alternatingWord_succ', if_pos he, List.cons_append])
          (by rw [braidWord, hm, alternatingWord_succ', if_pos he, List.cons_append])
      · exact bridge hu hs hru hrv (move i j)
          (by rw [braidWord, hm, alternatingWord_succ', if_neg he, List.cons_append])
          (by rw [braidWord, M.symmetric j i, hm, alternatingWord_succ', if_neg he, List.cons_append])
