lemma cauchyBinet {m : ℕ} {n : Type*} [Fintype n] [DecidableEq n] [LinearOrder n]
    {R : Type*} [CommRing R]
    (A : Matrix (Fin m) n R) (B : Matrix n (Fin m) R) :
    (A * B).det = ∑ S : {S : Finset n // S.card = m},
      (A.submatrix id (S.1.orderEmbOfFin S.2)).det *
      (B.submatrix (S.1.orderEmbOfFin S.2) id).det := by
  have h_cauchy_binet : ∀ (A : Matrix (Fin m) n R) (B : Matrix n (Fin m) R), Matrix.det (A * B) = ∑ σ : Fin m → n, (∏ i, A i (σ i)) * Matrix.det (Matrix.of (fun i j ↦ B (σ i) j)) := by
    intro A B
    let D := (Matrix.detRowAlternating (n := Fin m) (R := R)).toMultilinearMap
    calc
      _ = D (fun i => ∑ k, A i k • B k) := by
        apply congrArg Matrix.det
        ext i j
        simp [Matrix.mul_apply, Finset.sum_apply, smul_eq_mul]
      _ = ∑ σ : Fin m → n, D (fun i => A i (σ i) • B (σ i)) :=
        D.map_sum (fun i k => A i k • B k)
      _ = _ := Finset.sum_congr rfl fun σ _ => D.map_smul_univ (fun i => A i (σ i)) (fun i => B (σ i))
  -- Split the sum into injective and non-injective functions.
  let summand (σ : Fin m → n) := (∏ i, A i (σ i)) * Matrix.det (Matrix.of (fun i j ↦ B (σ i) j))
  have h_split : ∑ σ : Fin m → n, summand σ = ∑ σ : Fin m → n, if Function.Injective σ then summand σ else 0 := by
    dsimp only [summand]
    refine Finset.sum_congr rfl fun σ _ => ?_
    split_ifs with hσ <;> simp_all [Function.Injective]
    obtain ⟨i, j, hij, hne⟩ := hσ
    exact mul_eq_zero_of_right _ (Matrix.det_zero_of_row_eq hne (by ext1; simp only [of_apply, hij]))
  -- Group the sum by the image of the injective functions.
  have h_group : ∑ σ : Fin m → n, (if Function.Injective σ then summand σ else 0) = ∑ S : {S : Finset n // S.card = m}, ∑ σ : Fin m → n, (if Function.Injective σ ∧ Finset.image σ Finset.univ = S.val then summand σ else 0) := by
    rw [← Finset.sum_comm, Finset.sum_congr rfl]
    intro σ _
    by_cases hσ : Function.Injective σ
    · simp [hσ]
      rw [Finset.sum_eq_single ⟨Finset.image σ Finset.univ, by simp [Finset.card_image_of_injective _ hσ]⟩]
      · simp
      · grind
      · simp
    · simp [hσ]
  -- For each subset $S$ of size $m$, the inner sum is equal to the product of the determinants of the submatrices of $A$ and $B$ corresponding to $S$.
  have h_inner : ∀ S : {S : Finset n // S.card = m}, ∑ σ : Fin m → n, (if Function.Injective σ ∧ Finset.image σ Finset.univ = S.val then summand σ else 0) = Matrix.det (Matrix.submatrix A id (S.val.orderEmbOfFin S.property)) * Matrix.det (Matrix.submatrix B (S.val.orderEmbOfFin S.property) id) := by
    intro S
    have h_inner_sum : ∑ σ : Fin m → n, (if Function.Injective σ ∧ Finset.image σ Finset.univ = S.val then summand σ else 0) = ∑ τ : Equiv.Perm (Fin m), (∏ i, A i (S.val.orderEmbOfFin S.property (τ i))) * Matrix.det (Matrix.of (fun i j ↦ B (S.val.orderEmbOfFin S.property (τ i)) j)) := by
      dsimp only [summand]
      have h_inner_sum : Finset.filter (fun σ : Fin m → n => Function.Injective σ ∧ Finset.image σ Finset.univ = S.val) Finset.univ = Finset.image (fun τ : Equiv.Perm (Fin m) => fun i => S.val.orderEmbOfFin S.property (τ i)) Finset.univ := by
        ext σ
        simp [Finset.mem_image]
        constructor
        · intro hσ
          let u (i : Fin m) : S.val := ⟨σ i, hσ.2 ▸ Finset.mem_image_of_mem _ (Finset.mem_univ _)⟩
          let a (i : Fin m) := (S.val.orderIsoOfFin S.property).symm (u i)
          have ha (i : Fin m) : σ i = S.val.orderEmbOfFin S.property (a i) :=
            congrArg Subtype.val ((S.val.orderIsoOfFin S.property).apply_symm_apply (u i)).symm
          have ha_inj : Function.Injective a := by
            exact fun i j hij => hσ.1 <| by simp [ha, hij]
          exact ⟨Equiv.ofBijective a ⟨ha_inj, Finite.injective_iff_surjective.mp ha_inj⟩, funext fun i => ha i ▸ rfl⟩
        · rintro ⟨a, rfl⟩
          constructor
          · exact fun i j hij => a.injective <| by simpa using hij
          · refine Finset.eq_of_subset_of_card_le (Finset.image_subset_iff.mpr fun i _ => Finset.orderEmbOfFin_mem _ _ _) ?_
            rw [Finset.card_image_of_injective _ fun i j hij => by simpa [Fin.ext_iff] using hij]; simp [S.2]
      rw [← Finset.sum_filter, h_inner_sum, Finset.sum_image]
      exact fun τ _ τ' _ h => Equiv.Perm.ext fun i => by simpa using congr_fun h i
    rw [h_inner_sum, Matrix.det_apply', Matrix.det_apply']
    simp [Matrix.det_apply', Finset.sum_mul]
    refine' Finset.sum_bij (fun σ _ => σ⁻¹) _ _ _ _ <;> simp [Equiv.Perm.sign_inv]
    · exact fun b => ⟨b⁻¹, inv_inv b⟩
    · intro σ
      rw [← Equiv.prod_comp σ⁻¹]
      simp [mul_assoc, mul_left_comm, Finset.mul_sum]
      refine' Finset.sum_bij (fun τ _ => σ * τ) _ _ _ _ <;> simp [Equiv.Perm.sign_mul]
      · exact fun b => ⟨σ⁻¹ * b, by simp⟩
      · cases' Int.units_eq_one_or (Equiv.Perm.sign σ) with h h <;> simp [h]
  rw [h_cauchy_binet, h_split, h_group, Finset.sum_congr rfl fun S hS => h_inner S]
