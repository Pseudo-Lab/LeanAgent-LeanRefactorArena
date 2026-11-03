lemma pauliContr_mul_pauliContrDown_mul_pauliContr : ({
    σ^^^ | μ α β ⊗ σ^^^ | ν τ(α') τ(β) ⊗ σ^^^ | ρ α' β' =
      ((((η | μ ν ⊗ σ^^^ | ρ α β') + (-((η | μ ρ ⊗ σ^^^ | ν α β'))))
        + (η | ν ρ ⊗ σ^^^ | μ α β'))
        + (Complex.I •ₜ (ε4ℂ | μ ν ρ κ ⊗ σ^^^ | τ(κ) α β')))
    }ᵀ : Prop) := by
  simp_rw [pauliContr_mul_dualWeyl_eq_ofGaussianInt, leviCivita_mul_pauliDual]
  simp only [toTensor_eq_ofGaussianInt, contrMetric_eq_ofGaussianInt,
    leviCivita_eq_ofGaussianInt_prod, pauliCo_eq_ofGaussianInt,
    prodT_ofGaussianInt_ofGaussianInt, contrT_ofGaussianInt]
  apply (Tensor.basis _).repr.injective
  ext1
  simp only [map_add, map_neg, map_smul, Finsupp.add_apply,
    Finsupp.neg_apply, Finsupp.smul_apply, permT_basis_repr_symm_apply]
  simp only [ofGaussianInt_basis_repr_apply, smul_eq_mul,
    show Complex.I = GaussianInt.toComplex ⟨0, 1⟩ by
      simp [GaussianInt.toComplex_def'], ← GaussianInt.toComplex.map_add,
    ← GaussianInt.toComplex.map_neg, ← GaussianInt.toComplex.map_mul]
  apply congrArg
  decide +revert +kernel
