theorem RS_exists_nonzero_kernelVec_of_det_eq_zero_natDegree_le_one (e : ℕ)
    (K : Matrix (Fin (e + 1)) (Fin (e + 1)) F[X])
    (hdeg : ∀ i j, (K i j).natDegree ≤ 1)
    (hdet : Matrix.det K = 0) :
    ∃ a : Fin (e + 1) → F[X],
      a ≠ 0 ∧ (∀ t, (a t).natDegree ≤ e) ∧ Matrix.mulVec K a = 0 := by
  classical
  let n := e + 1
  let P : ℕ → Prop := fun r =>
    ∃ (I J : Fin r ↪ Fin n), Matrix.det (K.submatrix I J) ≠ 0
  have hP0 : P 0 := by
    refine ⟨Function.Embedding.ofIsEmpty, Function.Embedding.ofIsEmpty, ?_⟩
    simp
  let r : ℕ := Nat.findGreatest P n
  have hPr : P r := Nat.findGreatest_spec (Nat.zero_le n) hP0
  rcases hPr with ⟨I,J,hIJ⟩
  have hPn : ¬ P n := by
    rintro ⟨I0, J0, hdet0⟩
    exact hdet0 (RS_det_submatrix_eq_zero_of_det_eq_zero n K hdet I0 J0)
  have hr_lt : r < n :=
    lt_of_le_of_ne (Nat.findGreatest_le n) (fun h => hPn (h ▸ (show P r from ⟨I, J, hIJ⟩)))
  have hr_le_e : r ≤ e := Nat.lt_succ_iff.mp hr_lt
  have hnotP_succ : ¬ P (r + 1) :=
    Nat.findGreatest_is_greatest (Nat.lt_succ_self r) (Nat.succ_le_of_lt hr_lt)
  have missing (E : Fin r ↪ Fin n) : ∃ i, i ∉ Set.range E := by
    have hn : ¬ Function.Surjective E := by
      intro h
      have hc := Fintype.card_le_of_surjective E h
      simp only [Fintype.card_fin] at hc
      omega
    simpa only [Function.Surjective, Set.mem_range, not_forall] using hn
  obtain ⟨i0, hi0⟩ := missing I
  obtain ⟨j0, hj0⟩ := missing J
  let I' := Fin.Embedding.snoc I hi0
  let J' := Fin.Embedding.snoc J hj0
  let B := K.submatrix I' J'
  have hdetB : Matrix.det B = 0 := by
    by_contra h
    exact hnotP_succ ⟨I', J', h⟩
  let u := fun t => B.adjugate t (Fin.last r)
  have hBu : Matrix.mulVec B u = 0 :=
    RS_mulVec_adjugate_col_eq_zero_of_det_eq_zero (n := r + 1) (A := B) (j := Fin.last r) hdetB
  have hu_last : u (Fin.last r) ≠ 0 := by
    have hBsub : B.submatrix Fin.castSucc Fin.castSucc = K.submatrix I J := by
      ext i j : 2
      simp [B, I', J']
    change B.adjugate (Fin.last r) (Fin.last r) ≠ 0
    rw [RS_adjugate_last_last_eq_det_submatrix_castSucc_castSucc, hBsub]
    exact mul_ne_zero (by simp) hIJ
  let a := Function.extend J' u (fun _ => 0)
  have ha_on : ∀ t : Fin (r + 1), a (J' t) = u t :=
    J'.injective.extend_apply u (fun _ => 0)
  have hmulVec_eq (i : Fin n) :
      (Matrix.mulVec K a) i = ∑ j : Fin (r + 1), K i (J' j) * u j := by
    symm
    apply Fintype.sum_of_injective (e := J') J'.injective
    · intro j hj
      have hz : a j = 0 := Function.extend_apply' u (fun _ => 0) j hj
      simp [hz]
    · intro t
      rw [ha_on t]
  refine ⟨a,?_,?_,?_⟩
  · intro h
    apply hu_last
    simpa [h] using (ha_on (Fin.last r)).symm
  · intro t
    by_cases ht : ∃ s : Fin (r + 1), (J' s : Fin n) = t
    · rcases ht with ⟨s, rfl⟩
      rw [ha_on s]
      change (B.adjugate s (Fin.last r)).natDegree ≤ e
      rw [RS_adjugate_fin_succ_eq_det_submatrix_last_castSucc]
      apply Polynomial.natDegree_mul_le.trans
      simpa only [Polynomial.natDegree_pow, Polynomial.natDegree_neg,
        Polynomial.natDegree_one, mul_zero, zero_add] using
        (RS_natDegree_det_le_of_entry_natDegree_le_one r
          (B.submatrix Fin.castSucc s.succAbove) (fun i j => hdeg _ _)).trans hr_le_e
    · have hz : a t = 0 := Function.extend_apply' u (fun _ => 0) t ht
      simp [hz]
  · funext i
    rw [hmulVec_eq]
    by_cases hi : i ∈ Set.range I
    · rcases hi with ⟨t, rfl⟩
      simpa [B, I', Matrix.mulVec, dotProduct] using congrFun hBu (Fin.castSucc t)
    · let Ii : Fin (r + 1) ↪ Fin n := Fin.Embedding.snoc I hi
      let b : Fin (r + 1) → F[X] := fun j => K i (J' j)
      have hupdate : B.updateRow (Fin.last r) b = K.submatrix Ii J' := by
        ext irow jcol : 2
        cases irow using Fin.lastCases <;> simp [B, I', Ii, b, Matrix.updateRow]
      have hd : Matrix.det (B.updateRow (Fin.last r) b) = 0 := by
        rw [hupdate]
        by_contra h
        exact hnotP_succ ⟨Ii, J', h⟩
      exact (det_updateRow_eq_sum_mul_adjugate_col (A := B) (i := Fin.last r) (b := b)).symm.trans hd
