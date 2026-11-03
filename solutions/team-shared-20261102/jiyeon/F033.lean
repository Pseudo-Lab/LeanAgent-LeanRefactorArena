theorem fiberwise_dist_lt_imp_dist_lt_unique_decoding_radius (i : Fin ℓ) (steps : ℕ)
    [NeZero steps] (h_i_add_steps : i.val + steps ≤ ℓ)
    (f : OracleFunction 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩)
  (h_fw_dist_lt : fiberwiseClose 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate)
    (i := i) (steps := steps) (h_i_add_steps := h_i_add_steps) (f := f)) :
  hammingClose 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩ f := by
  unfold fiberwiseClose at h_fw_dist_lt
  unfold hammingClose
  let d_fw := fiberwiseDistance 𝔽q β (i := i) steps h_i_add_steps f
  let C_i := (BBF_Code 𝔽q β (h_ℓ_add_R_rate := h_ℓ_add_R_rate) ⟨i, by omega⟩)
  let d_H := Code.distFromCode f C_i
  let d_i := BBF_CodeDistance ℓ 𝓡 (⟨i, by omega⟩)
  let d_i_plus_steps := BBF_CodeDistance ℓ 𝓡 ⟨i.val + steps, by omega⟩
  have h_d_i_gt_0 : d_i > 0 := by
    dsimp [d_i, BBF_CodeDistance]
    omega
  have h_C_i_nonempty : Nonempty C_i := ⟨0⟩
  obtain ⟨g', h_g'_mem, h_g'_min_card⟩ : ∃ g' ∈ C_i, d_fw
    = (fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g').ncard := by
    let S := (fun (g : C_i) => (fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps
      f g).ncard) '' Set.univ
    obtain ⟨g, _, heq⟩ := Nat.sInf_mem
      (show S.Nonempty from Set.image_nonempty.mpr Set.univ_nonempty)
    exact ⟨g.val, g.property, heq.symm⟩
  have h_dist_le_fw_dist_times_fiber_size : (hammingDist f g' : ℕ∞) ≤ d_fw * 2 ^ steps := by
    change (Δ₀(f, g') : ℕ∞) ≤ ↑d_fw * ((2 ^ steps : ℕ) : ℕ∞)
    rw [←ENat.coe_mul, ENat.coe_le_coe, h_g'_min_card]
    set ΔH := Finset.filter (fun x => f x ≠ g' x) Finset.univ
    change ΔH.card ≤ _
    set Y_bad := fiberwiseDisagreementSet 𝔽q β i steps h_i_add_steps f g'
    letI : Fintype Y_bad := Fintype.ofFinite Y_bad
    have h_ΔH_subset_bad_fiber_points : ΔH ⊆ Finset.biUnion Y_bad.toFinset
        (t := fun y => ((qMap_total_fiber 𝔽q β (i := ⟨i, by omega⟩) (steps := steps)
          (h_i_add_steps := by apply Nat.lt_add_of_pos_right_of_le; omega) (y := y)) ''
          (Finset.univ : Finset (Fin ((2:ℕ)^steps)))).toFinset) := by
      intro x hx
      let y := iteratedQuotientMap 𝔽q β h_ℓ_add_R_rate i steps h_i_add_steps x
      refine Finset.mem_biUnion.mpr ⟨y, Set.mem_toFinset.mpr ⟨x, rfl, (Finset.mem_filter.mp hx).2⟩, ?_⟩
      simp only [coe_univ, Set.image_univ, Set.toFinset_range, mem_image, mem_univ, true_and]
      exact ⟨pointToIterateQuotientIndex (i := ⟨i, by omega⟩) (steps := steps)
        (h_i_add_steps := by omega) (x := x),
        (is_fiber_iff_generates_quotient_point 𝔽q β i steps (by omega) (x := x) (y := y)).mp rfl⟩
    apply (Finset.card_le_card h_ΔH_subset_bad_fiber_points).trans
    calc
      _ ≤ Y_bad.toFinset.card * 2 ^ steps := by
        apply Finset.card_biUnion_le_card_mul
        intro y hy
        simpa only [Finset.coe_univ, Set.image_univ, Set.toFinset_range,
          Finset.card_univ, Fintype.card_fin] using
          (Finset.card_image_le (s := Finset.univ)
            (f := qMap_total_fiber 𝔽q β (i := ⟨i, by omega⟩) (steps := steps)
              (h_i_add_steps := by apply Nat.lt_add_of_pos_right_of_le; omega) (y := y)))
      _ = _ := by simp only [Set.toFinset_card, ← Nat.card_coe_set_eq, Nat.card_eq_fintype_card]
  have h_dist_bridge : d_H ≤ d_fw * 2 ^ steps := by
    exact (Code.distFromCode_le_dist_to_mem f g' h_g'_mem).trans h_dist_le_fw_dist_times_fiber_size
  have h_fw_bound : 2 * d_fw ≤ d_i_plus_steps - 1 := Nat.le_of_lt_succ (WithTop.coe_lt_coe.1 h_fw_dist_lt)
  have h_algebraic_identity : (d_i_plus_steps - 1) * 2 ^ steps = d_i - 1 := by
    dsimp [d_i, d_i_plus_steps, BBF_CodeDistance]
    rw [Nat.sub_mul, ←Nat.pow_add, ←Nat.pow_add];
    congr 2 <;> omega
  have hnat : 2 * (d_fw * 2 ^ steps) < d_i := by
    apply Nat.lt_of_le_pred h_d_i_gt_0
    rw [Nat.pred_eq_sub_one, ← h_algebraic_identity, ← mul_assoc]
    exact Nat.mul_le_mul_right _ h_fw_bound
  change (2 : ℕ∞) * d_H < (d_i : ℕ∞)
  exact (mul_le_mul_left' h_dist_bridge 2).trans_lt (by exact_mod_cast hnat)
