lemma cauchyBinet {m : ℕ} {n : Type*} [Fintype n] [DecidableEq n] [LinearOrder n]
    {R : Type*} [CommRing R]
    (A : Matrix (Fin m) n R) (B : Matrix n (Fin m) R) :
    (A * B).det = ∑ S : {S : Finset n // S.card = m},
      (A.submatrix id (S.1.orderEmbOfFin S.2)).det *
      (B.submatrix (S.1.orderEmbOfFin S.2) id).det := by
  have hd (M : Matrix (Fin m) (Fin m) R) :
      M.det = ∑ τ : Equiv.Perm (Fin m), (∏ i, M i (τ i)) * (Equiv.Perm.sign τ : R) := by
    rw [← Matrix.det_transpose M, Matrix.det_apply']
    exact Finset.sum_congr rfl fun _ _ => mul_comm _ _
  have h_cauchy_binet : (A * B).det = ∑ σ : Fin m → n,
      (∏ i, A i (σ i)) * Matrix.det (Matrix.of (fun i j ↦ B (σ i) j)) := by
    simp only [hd, Matrix.mul_apply, Matrix.of_apply, Finset.mul_sum]
    rw [← Finset.sum_comm]
    refine Finset.sum_congr rfl fun x _ => ?_
    simp only [prod_sum, sum_mul]
    refine' Finset.sum_bij (fun f _ i => f i (Finset.mem_univ _)) _ _ _ _
    · exact fun _ _ => Finset.mem_univ _
    · simp only [univ_pi_univ, mem_univ, funext_iff, forall_true_left, forall_const]
      exact fun _ _ h => h
    · simp only [mem_univ, univ_pi_univ, exists_const, forall_const]
      exact fun b => ⟨fun i _ => b i, rfl⟩
    · simp only [univ_pi_univ, mem_univ, prod_mul_distrib, prod_attach_univ, forall_const]
      intro a
      ac_rfl
  let f := fun σ : Fin m → n => (∏ i, A i (σ i)) * Matrix.det (Matrix.of (fun i j ↦ B (σ i) j))
  rw [h_cauchy_binet]
  change (∑ σ, f σ) = _
  trans ∑ S : {S : Finset n // S.card = m}, ∑ σ,
    if Function.Injective σ ∧ Finset.image σ Finset.univ = S.val then f σ else 0
  · rw [← Finset.sum_comm]
    refine Finset.sum_congr rfl fun σ _ => ?_
    by_cases hσ : Function.Injective σ
    · simp only [hσ, true_and]
      rw [Finset.sum_eq_single ⟨Finset.image σ Finset.univ, by
        simp only [Finset.card_image_of_injective _ hσ, card_univ, Fintype.card_fin]⟩]
      · exact (if_pos rfl).symm
      · intro T _ hT
        exact if_neg (fun h => hT (Subtype.ext h.symm))
      · simp only [mem_univ, not_true_eq_false, false_implies]
    · simp only [hσ, false_and, ↓reduceIte, Finset.sum_const_zero]
      simp only [Function.Injective, not_forall] at hσ
      obtain ⟨i, j, hij, hne⟩ := hσ
      exact mul_eq_zero_of_right _ (Matrix.det_zero_of_row_eq hne (by
        ext1
        simp only [of_apply, hij]))
  · refine Finset.sum_congr rfl fun S _ => ?_
    let e := S.val.orderEmbOfFin S.property
    have he : Finset.image e Finset.univ = S.val := by
      refine Finset.eq_of_subset_of_card_le
        (Finset.image_subset_iff.mpr fun i _ => Finset.orderEmbOfFin_mem _ _ _) ?_
      rw [Finset.card_image_of_injective _ e.injective]
      simp only [card_univ, Fintype.card_fin, S.2, le_refl]
    have hf : Finset.filter (fun σ : Fin m → n => Function.Injective σ ∧ Finset.image σ Finset.univ = S.val) Finset.univ =
        Finset.image (fun τ : Equiv.Perm (Fin m) => fun i => e (τ i)) Finset.univ := by
      ext σ
      simp only [mem_filter, mem_univ, true_and, mem_image]
      constructor
      · intro hσ
        have h_exists_a : ∀ i, ∃ a : Fin m, σ i = e a := by
          intro i
          have hmem : σ i ∈ Finset.image e Finset.univ := by
            rw [he, ← hσ.2]
            exact Finset.mem_image_of_mem _ (Finset.mem_univ _)
          obtain ⟨a, _, ha⟩ := Finset.mem_image.mp hmem
          exact ⟨a, ha.symm⟩
        choose a ha using h_exists_a
        have ha_inj : Function.Injective a :=
          fun i j hij => hσ.1 <| by simp only [ha, hij]
        exact ⟨Equiv.ofBijective a ⟨ha_inj, Finite.injective_iff_surjective.mp ha_inj⟩,
          funext fun i => (ha i).symm⟩
      · rintro ⟨a, rfl⟩
        constructor
        · exact e.injective.comp a.injective
        · refine Finset.eq_of_subset_of_card_le
            (Finset.image_subset_iff.mpr fun i _ => Finset.orderEmbOfFin_mem _ _ _) ?_
          rw [Finset.card_image_of_injective _ (show Function.Injective (fun i => e (a i)) from e.injective.comp a.injective)]
          simp only [card_univ, Fintype.card_fin, S.2, le_refl]
    rw [← Finset.sum_filter, hf, Finset.sum_image]
    · rw [hd (A.submatrix id e), Finset.sum_mul]
      refine Finset.sum_congr rfl fun τ _ => ?_
      change (∏ i, A i (e (τ i))) * ((B.submatrix e id).submatrix τ id).det = _
      rw [Matrix.det_permute]
      ac_rfl
    · exact fun τ _ τ' _ h => Equiv.Perm.ext fun i => e.injective (congr_fun h i)