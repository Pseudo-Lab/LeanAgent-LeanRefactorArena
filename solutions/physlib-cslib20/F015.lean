lemma pauliContr_mul_pauliContrDown_mul_pauliContr : ({
    σ^^^ | μ α β ⊗ σ^^^ | ν τ(α') τ(β) ⊗ σ^^^ | ρ α' β' =
      ((((η | μ ν ⊗ σ^^^ | ρ α β') + (-((η | μ ρ ⊗ σ^^^ | ν α β'))))
        + (η | ν ρ ⊗ σ^^^ | μ α β'))
        + (Complex.I •ₜ (ε4ℂ | μ ν ρ κ ⊗ σ^^^ | τ(κ) α β')))
    }ᵀ : Prop) := by
  conv_lhs =>
    rw [pauliContr_mul_dualWeyl_eq_ofGaussianInt, toTensor_eq_ofGaussianInt,
      prodT_ofGaussianInt_ofGaussianInt, contrT_ofGaussianInt]
  conv_rhs =>
    rw [leviCivita_mul_pauliDual]
    simp only [contrMetric_eq_ofGaussianInt, toTensor_eq_ofGaussianInt,
      prodT_ofGaussianInt_ofGaussianInt]
    simp only [leviCivita_eq_ofGaussianInt_prod, pauliCo_eq_ofGaussianInt]
    rw [prodT_ofGaussianInt_ofGaussianInt, contrT_ofGaussianInt, permT_ofGaussianInt]
  apply (Tensor.basis _).repr.injective
  ext b
  rw [ofGaussianInt_basis_repr_apply, permT_basis_repr_symm_apply]
  simp only [map_add, Finsupp.coe_add, Pi.add_apply]
  simp only [permT_basis_repr_symm_apply, map_neg, Finsupp.coe_neg, Pi.neg_apply,
    map_smul, Finsupp.coe_smul, Pi.smul_apply, smul_eq_mul, ofGaussianInt_basis_repr_apply]
  conv_rhs => arg 2; rw [show ∀ a : GaussianInt, Complex.I * GaussianInt.toComplex a =
    GaussianInt.toComplex (⟨0, 1⟩ * a) from fun a => by simp [GaussianInt.toComplex_def']]
  apply (show ∀ a b c d e : GaussianInt, a = b + -c + d + e → GaussianInt.toComplex a =
    GaussianInt.toComplex b + -GaussianInt.toComplex c + GaussianInt.toComplex d +
      GaussianInt.toComplex e from fun _ _ _ _ _ h => by simp [h])
  decide +revert +kernel
