lemma pauliContrDown_mul_pauliContr_mul_pauliContrDown : ({
    σ^^^ | μ τ(α) τ(β) ⊗ σ^^^ | ν α β' ⊗ σ^^^ | ρ τ(α') τ(β') =
      ((((η | μ ν ⊗ σ^^^ | ρ τ(α') τ(β))
        + (-((η | μ ρ ⊗ σ^^^ | ν τ(α') τ(β)))))
        + (η | ν ρ ⊗ σ^^^ | μ τ(α') τ(β)))
        + ((-Complex.I) •ₜ (ε4ℂ | μ ν ρ κ ⊗ σ^^^ | τ(κ) τ(α') τ(β))))
    }ᵀ : Prop) := by
  conv_lhs =>
    rw [dualWeyl_mul_pauliContr_eq_ofGaussianInt, toTensor_dualWeyl_eq_ofGaussianInt,
      prodT_ofGaussianInt_ofGaussianInt, contrT_ofGaussianInt]
  conv_rhs =>
    simp only [contrMetric_eq_ofGaussianInt, toTensor_dualWeyl_eq_ofGaussianInt,
      prodT_ofGaussianInt_ofGaussianInt]
    simp only [leviCivita_eq_ofGaussianInt_prod, toTensor_dualAll_eq_ofGaussianInt]
    rw [prodT_ofGaussianInt_ofGaussianInt, contrT_ofGaussianInt, permT_ofGaussianInt]
  apply (Tensor.basis _).repr.injective
  ext b
  rw [ofGaussianInt_basis_repr_apply, permT_basis_repr_symm_apply]
  simp only [map_add, Finsupp.coe_add, Pi.add_apply]
  simp only [permT_basis_repr_symm_apply, map_neg, Finsupp.coe_neg, Pi.neg_apply,
    map_smul, Finsupp.coe_smul, Pi.smul_apply, smul_eq_mul, ofGaussianInt_basis_repr_apply]
  conv_rhs => arg 2; rw [show ∀ a : GaussianInt, -Complex.I * GaussianInt.toComplex a =
    GaussianInt.toComplex (-⟨0, 1⟩ * a) from fun a => by simp [GaussianInt.toComplex_def']]
  apply (show ∀ a b c d e : GaussianInt, a = b + -c + d + e → GaussianInt.toComplex a =
    GaussianInt.toComplex b + -GaussianInt.toComplex c + GaussianInt.toComplex d +
      GaussianInt.toComplex e from fun _ _ _ _ _ h => by simp [h])
  decide +revert +kernel
