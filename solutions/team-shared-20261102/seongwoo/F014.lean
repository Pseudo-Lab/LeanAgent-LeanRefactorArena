lemma pauliContrDown_mul_pauliContr_mul_pauliContrDown : ({
    σ^^^ | μ τ(α) τ(β) ⊗ σ^^^ | ν α β' ⊗ σ^^^ | ρ τ(α') τ(β') =
      ((((η | μ ν ⊗ σ^^^ | ρ τ(α') τ(β))
        + (-((η | μ ρ ⊗ σ^^^ | ν τ(α') τ(β)))))
        + (η | ν ρ ⊗ σ^^^ | μ τ(α') τ(β)))
        + ((-Complex.I) •ₜ (ε4ℂ | μ ν ρ κ ⊗ σ^^^ | τ(κ) τ(α') τ(β))))
    }ᵀ : Prop) := by
  simp_rw [dualWeyl_mul_pauliContr_eq_ofGaussianInt]
  simp only [toTensor_dualWeyl_eq_ofGaussianInt, contrMetric_eq_ofGaussianInt,
    leviCivita_eq_ofGaussianInt_prod, toTensor_dualAll_eq_ofGaussianInt,
    prodT_ofGaussianInt_ofGaussianInt, contrT_ofGaussianInt, permT_ofGaussianInt]
  apply (Tensor.basis _).repr.injective
  ext1
  simp only [permT_basis_repr_symm_apply, map_add, Finsupp.add_apply,
    map_neg, Finsupp.neg_apply, map_smul, Finsupp.smul_apply,
    smul_eq_mul, ofGaussianInt_basis_repr_apply]
  simp only [show Complex.I = GaussianInt.toComplex ⟨0, 1⟩ by
    simp [GaussianInt.toComplex_def'], ← GaussianInt.toComplex.map_mul,
    ← GaussianInt.toComplex.map_neg, ← GaussianInt.toComplex.map_add]
  apply congrArg GaussianInt.toComplex
  decide +revert +kernel
