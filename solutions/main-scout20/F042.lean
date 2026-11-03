theorem matsumoto_reduced_aux [MatsumotoCondition cs] (p : ℕ) (l l' : List B)
(len_l_eq_p : l.length = p) (len_l'_eq_p : l'.length = p)
(l_reduced : cs.IsReduced l) (l'_reduced : cs.IsReduced l') (h_eq : π l = π l') :
  ∃ bms : List (cs.BraidMove), cs.applyBraidMoveSequence bms l = l' := by
  induction p generalizing l l' with
  | zero =>
    rw [List.length_eq_zero_iff.mp len_l_eq_p, List.length_eq_zero_iff.mp len_l'_eq_p]
    exact ⟨[], rfl⟩
  | succ p ih =>
    obtain ⟨i, u, rfl, hu⟩ := cons_of_length_succ l len_l_eq_p
    obtain ⟨j, v, rfl, hv⟩ := cons_of_length_succ l' len_l'_eq_p
    have step := fun a x y hx hy =>
      cs.matsumoto_reduced_inductionStep_of_firstLetterEq p x y a
        (Nat.succ.inj hx) (Nat.succ.inj hy) (ih := ih)
    by_cases hij : i = j
    · subst j
      exact step i u v len_l_eq_p len_l'_eq_p h_eq l_reduced l'_reduced
    · have bridge (a b : B) (t x y : List B)
          (ht : π (i :: u) = π (braidWord M a b ++ t))
          (hr : cs.IsReduced (braidWord M a b ++ t))
          (hx : braidWord M a b ++ t = i :: x)
          (hy : braidWord M b a ++ t = j :: y) :
          ∃ bms, cs.applyBraidMoveSequence bms (i :: u) = j :: v := by
        have he : π (braidWord M a b ++ t) = π (braidWord M b a ++ t) := by
          rw [wordProd_append, wordProd_append, cs.wordProd_braidWord_eq a b]
        have hs := cs.isReduced_of_eq_length _ _
          (by simp only [List.length_append, length_alternatingWord, M.symmetric a b]) he hr
        simp only [hx, hy] at ht hr he hs
        have la := (cs.eq_length_of_isReduced _ _ ht l_reduced hr).symm.trans len_l_eq_p
        have hb := he.symm.trans (ht.symm.trans h_eq)
        have lb := (cs.eq_length_of_isReduced _ _ hb hs l'_reduced).trans len_l'_eq_p
        obtain ⟨bs, hs₁⟩ := step i u x len_l_eq_p la ht l_reduced hr
        obtain ⟨bs', hs₂⟩ := step j y v lb len_l'_eq_p hb hs l'_reduced
        refine ⟨bs' ++ BraidMove.mk a b 0 :: bs, ?_⟩
        rw [apply_braidMove_sequence_append, apply_braidMoveSequence_cons, hs₁, ← hx,
          applyBraidMove, ← length_alternatingWord a b (M a b), List.take_left,
          if_pos rfl, List.drop_left, hy, hs₂]
      obtain ⟨n, hn⟩ : ∃ n, M i j = n + 1 :=
        ⟨M i j - 1, by simp [MatsumotoCondition.one_le_M cs i j]⟩
      have hn' := (M.symmetric j i).trans hn
      by_cases hnEven : Even n
      · obtain ⟨t, ht, hr⟩ := cs.prefix_braidWord v u j i (Ne.symm hij) h_eq.symm l'_reduced l_reduced
        apply bridge j i t (alternatingWord j i n ++ t) (alternatingWord i j n ++ t) (h_eq.trans ht) hr <;>
          simp only [braidWord, hn, hn', alternatingWord_succ', if_pos hnEven, List.cons_append]
      · obtain ⟨t, ht, hr⟩ := cs.prefix_braidWord u v i j hij h_eq l_reduced l'_reduced
        apply bridge i j t (alternatingWord i j n ++ t) (alternatingWord j i n ++ t) ht hr <;>
          simp only [braidWord, hn, hn', alternatingWord_succ', if_neg hnEven, List.cons_append]
