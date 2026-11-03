lemma inv_convex {x y : HermitianMat d 𝕜} (hx : x.mat.PosDef) (hy : y.mat.PosDef)
    ⦃a b : ℝ⦄ (ha : 0 ≤ a) (hb : 0 ≤ b) (hab : a + b = 1) :
    (a • x + b • y)⁻¹ ≤ a • x⁻¹ + b • y⁻¹ := by
  -- Using the fact that the set of positive semidefinite matrices is a convex cone, we can show that the matrix
  -- $\begin{pmatrix} a \bullet x + b \bullet y & I \\ I & a \bullet x^{-1} + b \bullet y^{-1} \end{pmatrix}$
  -- is positive semidefinite.
  have h_pos_semidef :
    (Matrix.fromBlocks (a • x.mat + b • y.mat) (1 : Matrix d d 𝕜) (1 : Matrix d d 𝕜) (a • (x.mat)⁻¹ + b • (y.mat)⁻¹)).PosSemidef := by
      -- Since $a + b = 1$, we can use the fact that the block matrix $\begin{pmatrix} A & I \\ I & A^{-1} \end{pmatrix}$ is positive semidefinite for any positive definite $A$.
      have h_block_pos : ∀ A : Matrix d d 𝕜, A.PosDef → (Matrix.fromBlocks A 1 1 A⁻¹).PosSemidef := by
        intro A hA
        letI := hA.isUnit.invertible
        simpa using (Matrix.PosDef.fromBlocks₁₁ (1 : Matrix d d 𝕜) A⁻¹ hA).2 (by simp [Matrix.PosSemidef.zero])
      -- Since $a + b = 1$, we can use the fact that the block matrix $\begin{pmatrix} a \bullet x + b \bullet y & I \\ I & a \bullet x^{-1} + b \bullet y^{-1} \end{pmatrix}$ is positive semidefinite.
      simpa only [Matrix.fromBlocks_smul, Matrix.fromBlocks_add, ← add_smul, hab, one_smul] using ((h_block_pos _ hx).smul ha).add ((h_block_pos _ hy).smul hb)
  have h_schur : (a • x.mat + b • y.mat).PosDef := by
    rcases ha.eq_or_lt with h | h
    · have hb1 : b = 1 := by linarith
      simpa [← h, hb1] using hy
    · exact (hx.smul h).add_posSemidef (hy.posSemidef.smul hb)
  change (a • (x.mat)⁻¹ + b • (y.mat)⁻¹ - (a • x.mat + b • y.mat)⁻¹).PosSemidef
  letI := h_schur.isUnit.invertible
  simpa using (Matrix.PosDef.fromBlocks₁₁ (1 : Matrix d d 𝕜) _ h_schur).1 (by simpa using h_pos_semidef)
