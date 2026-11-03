lemma inv_convex {x y : HermitianMat d 𝕜} (hx : x.mat.PosDef) (hy : y.mat.PosDef)
    ⦃a b : ℝ⦄ (ha : 0 ≤ a) (hb : 0 ≤ b) (hab : a + b = 1) :
    (a • x + b • y)⁻¹ ≤ a • x⁻¹ + b • y⁻¹ := by
  have h_schur : (a • x.mat + b • y.mat).PosDef := by
    by_cases h : a = 0
    · rw [h, zero_add] at hab
      simpa [h, hab] using hy
    · exact (hx.smul (ha.lt_of_ne' h)).add_posSemidef $
        hy.posSemidef.smul hb
  let z := (a • x.mat + b • y.mat)⁻¹
  have hquad (A : Matrix d d 𝕜) (hA : A.PosDef) :
      (A⁻¹ - z - z + z * A * z).PosSemidef := by
    have hu := isUnit_iff_ne_zero.mpr hA.det_pos.ne'
    convert hA.posSemidef.conjTranspose_mul_mul_same (A⁻¹ - z) using 1
    rw [Matrix.conjTranspose_sub, hA.inv.posSemidef.1,
      h_schur.inv.posSemidef.1]
    simp only [sub_mul, mul_sub, Matrix.mul_assoc,
      Matrix.mul_nonsing_inv _ hu, mul_one]
    simp only [← Matrix.mul_assoc, Matrix.nonsing_inv_mul _ hu, one_mul]
    abel
  have hsum : a • (z * x.mat * z) + b • (z * y.mat * z) = z := by
    simpa only [mul_add, add_mul, smul_mul_assoc, mul_smul_comm, one_mul] using
      congrArg (· * z) $ Matrix.nonsing_inv_mul _ $
        isUnit_iff_ne_zero.mpr h_schur.det_pos.ne'
  change (a • x.mat⁻¹ + b • y.mat⁻¹ - z).PosSemidef
  convert ((hquad _ hx).smul ha).add ((hquad _ hy).smul hb) using 1
  simp only [smul_add, smul_sub]
  calc
    _ = a • x.mat⁻¹ + b • y.mat⁻¹ -
        (a • z + b • z) - (a • z + b • z) +
        (a • (z * x.mat * z) + b • (z * y.mat * z)) := by
      simp only [← add_smul, hab, one_smul, hsum, sub_add_cancel]
    _ = _ := by abel
