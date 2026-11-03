theorem RS_exists_nonzero_kernelVec_of_det_eq_zero_natDegree_le_one (e : ℕ)
    (K : Matrix (Fin (e + 1)) (Fin (e + 1)) F[X])
    (hdeg : ∀ i j, (K i j).natDegree ≤ 1)
    (hdet : Matrix.det K = 0) :
    ∃ a : Fin (e + 1) → F[X],
      a ≠ 0 ∧ (∀ t, (a t).natDegree ≤ e) ∧ Matrix.mulVec K a = 0 := by
  classical
  let n : ℕ := e + 1
  let P : ℕ → Prop := fun r =>
    ∃ (I J : Fin r ↪ Fin n), Matrix.det (K.submatrix I J) ≠ 0
  have hP0 : P 0 := by
    refine ⟨Function.Embedding.ofIsEmpty, Function.Embedding.ofIsEmpty, ?_⟩
    simp
  let r : ℕ := Nat.findGreatest P n
  have hPr : P r := by
    have h :=
      Nat.findGreatest_spec (P := P) (m := 0) (n := n) (Nat.zero_le n) hP0
    simpa [r] using h
  rcases hPr with ⟨I, J, hIJ⟩
  have hPn : ¬ P n := by
    intro h
    rcases h with ⟨I0, J0, hdet0⟩
    have hzero := RS_det_submatrix_eq_zero_of_det_eq_zero n K hdet I0 J0
    exact hdet0 hzero
  have hr_le : r ≤ n := by
    simpa [r] using (Nat.findGreatest_le (P := P) n)
  have hr_lt : r < n := by
    have hr_ne : r ≠ n := by
      intro hEq
      have : P n := by
        simpa [hEq] using (show P r from ⟨I, J, hIJ⟩)
      exact hPn this
    exact lt_of_le_of_ne hr_le hr_ne
  have hr_le_e : r ≤ e := by
    have : r < e + 1 := by
      simpa [n] using hr_lt
    exact (Nat.lt_succ_iff.mp this)
  have hnotP_succ : ¬ P (r + 1) := by
    have hr1_le : r + 1 ≤ n := Nat.succ_le_of_lt hr_lt
    have hk : Nat.findGreatest P n < r + 1 := by
      simp [r]
    exact Nat.findGreatest_is_greatest (P := P) (n := n) (k := r + 1) hk hr1_le
  have hcard_lt_I : (Finset.univ.map I).card < (Finset.univ : Finset (Fin n)).card := by
    simpa [Finset.card_map, Finset.card_univ, Fintype.card_fin] using hr_lt
  obtain ⟨i0, -, hi0_not_mem⟩ := Finset.exists_mem_notMem_of_card_lt_card hcard_lt_I
  have hi0 : i0 ∉ Set.range I := by
    intro hi
    rcases hi with ⟨t, rfl⟩
    have : (I t) ∈ (Finset.univ.map I) := by
      simp
    exact hi0_not_mem this
  have hcard_lt_J : (Finset.univ.map J).card < (Finset.univ : Finset (Fin n)).card := by
    simpa [Finset.card_map, Finset.card_univ, Fintype.card_fin] using hr_lt
  obtain ⟨j0, -, hj0_not_mem⟩ := Finset.exists_mem_notMem_of_card_lt_card hcard_lt_J
  have hj0 : j0 ∉ Set.range J := by
    intro hj
    rcases hj with ⟨t, rfl⟩
    have : (J t) ∈ (Finset.univ.map J) := by
      simp
    exact hj0_not_mem this
  let I' : Fin (r + 1) ↪ Fin n := Fin.Embedding.snoc I hi0
  let J' : Fin (r + 1) ↪ Fin n := Fin.Embedding.snoc J hj0
  let B : Matrix (Fin (r + 1)) (Fin (r + 1)) F[X] := K.submatrix I' J'
  have hdetB : Matrix.det B = 0 := by
    by_contra h
    exact hnotP_succ ⟨I', J', h⟩
  let u : Fin (r + 1) → F[X] := fun t => B.adjugate t (Fin.last r)
  have hBu : Matrix.mulVec B u = 0 := by
    simpa [u] using
      (RS_mulVec_adjugate_col_eq_zero_of_det_eq_zero (n := r + 1) (A := B) (j := Fin.last r) hdetB)
  have hu_last : u (Fin.last r) ≠ 0 := by
    have hAdj := RS_adjugate_last_last_eq_det_submatrix_castSucc_castSucc (n := r) (B := B)
    have hBsub : B.submatrix Fin.castSucc Fin.castSucc = K.submatrix I J := by
      ext i j
      simp [B, I', J']
    have hUL :
        u (Fin.last r) =
          (-1 : F[X]) ^ ((Fin.last r : ℕ) + (Fin.last r : ℕ)) * Matrix.det (K.submatrix I J) := by
      dsimp [u]
      rw [hAdj]
      simp [hBsub]
    have hsign :
        ((-1 : F[X]) ^ ((Fin.last r : ℕ) + (Fin.last r : ℕ))) ≠ 0 := by
      have hbase : (-1 : F[X]) ≠ 0 := by
        simp
      exact pow_ne_zero _ hbase
    rw [hUL]
    exact mul_ne_zero hsign hIJ
  have hu_ne : u ≠ 0 := by
    intro hu0
    have h := congrArg (fun f => f (Fin.last r)) hu0
    have : u (Fin.last r) = 0 := by
      simpa using h
    exact hu_last this
  have hu_deg : ∀ t, (u t).natDegree ≤ e := by
    intro t
    have hAdj :
        u t =
          (-1 : F[X]) ^ ((Fin.last r : ℕ) + (t : ℕ)) *
            Matrix.det (B.submatrix Fin.castSucc t.succAbove) := by
      dsimp [u]
      exact RS_adjugate_fin_succ_eq_det_submatrix_last_castSucc (n := r) (B := B) (t := t)
    let M : Matrix (Fin r) (Fin r) F[X] := B.submatrix Fin.castSucc t.succAbove
    have hdegM : ∀ i j, (M i j).natDegree ≤ 1 := by
      intro i j
      dsimp [M, B]
      exact hdeg (I' (Fin.castSucc i)) (J' (t.succAbove j))
    have hdetMdeg : (Matrix.det M).natDegree ≤ r :=
      RS_natDegree_det_le_of_entry_natDegree_le_one r M hdegM
    have hmuldeg : (u t).natDegree ≤ (Matrix.det M).natDegree := by
      rw [hAdj]
      dsimp [M]
      have hconst :
          (-1 : F[X]) ^ (r + (t : ℕ)) = Polynomial.C ((-1 : F) ^ (r + (t : ℕ))) := by
        simp
      rw [hconst]
      exact Polynomial.natDegree_C_mul_le _ _
    have : (u t).natDegree ≤ r := le_trans hmuldeg hdetMdeg
    exact le_trans this hr_le_e
  let a : Fin n → F[X] := Function.extend (J' : Fin (r + 1) → Fin n) u (fun _ => 0)
  have ha_on : ∀ t : Fin (r + 1), a (J' t) = u t := by
    intro t
    simpa [a] using (J'.injective.extend_apply u (fun _ => 0) t)
  have ha_ne : a ≠ 0 := by
    intro ha0
    have h := congrArg (fun f => f (J' (Fin.last r))) ha0
    have ha_last : a (J' (Fin.last r)) = 0 := by
      simpa using h
    have : u (Fin.last r) = 0 := by
      calc
        u (Fin.last r) = a (J' (Fin.last r)) := by
          symm
          exact ha_on (Fin.last r)
        _ = 0 := ha_last
    exact hu_last this
  have ha_deg : ∀ t, (a t).natDegree ≤ e := by
    intro t
    by_cases ht : ∃ s : Fin (r + 1), (J' s : Fin n) = t
    · rcases ht with ⟨s, rfl⟩
      simpa [ha_on s] using hu_deg s
    · have : a t = 0 := by
        simpa [a] using
          (Function.extend_apply' (f := (J' : Fin (r + 1) → Fin n)) (g := u) (e' := fun _ => 0)
            (b := t) ht)
      simp [this]
  have hmulVec_eq (i : Fin n) :
      (Matrix.mulVec K a) i = ∑ j : Fin (r + 1), K i (J' j) * u j := by
    classical
    have houtside :
        ∀ j : Fin n,
          j ∉ Set.range (J' : Fin (r + 1) → Fin n) → K i j * a j = 0 := by
      intro j hj
      have hj' : ¬ ∃ t : Fin (r + 1), (J' t : Fin n) = j := hj
      have ha0 : a j = 0 := by
        simpa [a] using
          (Function.extend_apply' (f := (J' : Fin (r + 1) → Fin n)) (g := u) (e' := fun _ => 0)
            (b := j) hj')
      simp [ha0]
    have hsum :
        (∑ j : Fin n, K i j * a j) = ∑ t : Fin (r + 1), K i (J' t) * a (J' t) := by
      have h :=
        (Fintype.sum_of_injective (e := (J' : Fin (r + 1) → Fin n)) (he := J'.injective)
          (f := fun t : Fin (r + 1) => K i (J' t) * a (J' t))
          (g := fun j : Fin n => K i j * a j) (h' := houtside) (h := fun t => rfl))
      exact h.symm
    calc
      (Matrix.mulVec K a) i = ∑ j : Fin n, K i j * a j := by
        rfl
      _ = ∑ t : Fin (r + 1), K i (J' t) * a (J' t) := hsum
      _ = ∑ t : Fin (r + 1), K i (J' t) * u t := by
        refine Fintype.sum_congr _ _ ?_
        intro t
        rw [ha_on t]
  have hKa : Matrix.mulVec K a = 0 := by
    funext i
    have hrewrite := hmulVec_eq i
    by_cases hi : i ∈ Set.range I
    · rcases hi with ⟨t, rfl⟩
      have hBu_t : (Matrix.mulVec B u) (Fin.castSucc t) = 0 := by
        have := congrArg (fun f => f (Fin.castSucc t)) hBu
        simpa using this
      have hBsum :
          (Matrix.mulVec B u) (Fin.castSucc t) = ∑ j : Fin (r + 1), K (I t) (J' j) * u j := by
        simp [B, I', Matrix.mulVec, dotProduct]
      have hsum0 : (∑ j : Fin (r + 1), K (I t) (J' j) * u j) = 0 := by
        simpa [hBsum] using hBu_t
      exact hrewrite.trans hsum0
    · have hi' : i ∉ Set.range I := hi
      let Ii : Fin (r + 1) ↪ Fin n := Fin.Embedding.snoc I hi'
      let b : Fin (r + 1) → F[X] := fun j => K i (J' j)
      have hupdate : B.updateRow (Fin.last r) b = K.submatrix Ii J' := by
        ext irow jcol
        cases irow using Fin.lastCases with
        | last =>
            simp [B, I', Ii, b, Matrix.updateRow]
        | cast t =>
            simp [B, I', Ii, b, Matrix.updateRow]
      have hdetBi : Matrix.det (K.submatrix Ii J') = 0 := by
        by_contra h
        exact hnotP_succ ⟨Ii, J', h⟩
      have hdetUpdate : Matrix.det (B.updateRow (Fin.last r) b) = 0 := by
        simpa [hupdate] using hdetBi
      have hsum_eq_det :
          (∑ j : Fin (r + 1), K i (J' j) * u j) = Matrix.det (B.updateRow (Fin.last r) b) := by
        simpa [b, u] using
          (det_updateRow_eq_sum_mul_adjugate_col (A := B) (i := Fin.last r) (b := b)).symm
      have hsum0 : (∑ j : Fin (r + 1), K i (J' j) * u j) = 0 := by
        simpa [hsum_eq_det] using hdetUpdate
      exact hrewrite.trans hsum0
  refine ⟨a, ha_ne, ha_deg, ?_⟩
  simpa [a, n] using hKa