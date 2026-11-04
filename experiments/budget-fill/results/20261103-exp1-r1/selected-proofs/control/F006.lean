theorem liftBVars_denote
    {e : LExpr T.mono} {τ : LMonoTy}
    {Δ₁ Δ_insert Δ_outer : List LMonoTy}
    (h_orig : LExpr.HasTypeA (Δ₁ ++ Δ_outer) e τ)
    (h_lifted : LExpr.HasTypeA (Δ₁ ++ (Δ_insert ++ Δ_outer)) (LExpr.liftBVars Δ_insert.length e Δ₁.length) τ)
    (bv₁ : BVarVal tcInterp vt Δ₁)
    (bv_insert : BVarVal tcInterp vt Δ_insert)
    (bv_outer : BVarVal tcInterp vt Δ_outer)
    : LExpr.denote tcInterp opInterp fvarVal vt (HList.append bv₁ (HList.append bv_insert bv_outer))
        (LExpr.liftBVars Δ_insert.length e Δ₁.length) τ h_lifted =
      LExpr.denote tcInterp opInterp fvarVal vt (HList.append bv₁ bv_outer) e τ h_orig := by
  induction e generalizing Δ₁ τ with
  | const => rfl
  | op _ _ ty | fvar _ _ ty => cases ty <;> rfl
  | bvar m i =>
    induction bv₁ generalizing i with
    | nil =>
      simp only [List.length_nil, LExpr.liftBVars, Nat.zero_le, ite_true] at h_lifted ⊢
      rw [denote_bvar, denote_bvar]
      simpa [HList.append] using
        (HList.get_append_right bv_insert bv_outer (i + Δ_insert.length)
          (HasTypeA.bvar_inv h_lifted)
          (by simpa using HasTypeA.bvar_inv h_orig) (by omega))
    | cons x xs ih =>
      rename_i a as
      cases i with
      | zero => simp [LExpr.liftBVars, denote_bvar, HList.append, HList.get]
      | succ i =>
        by_cases hc : as.length ≤ i
        all_goals
          simp [LExpr.liftBVars, Nat.succ_add, hc] at h_lifted
          simpa [LExpr.liftBVars, LExpr.denote, HList.append, HList.get, Nat.succ_add, hc] using
            ih (i := i)
              (by constructor; simpa using HasTypeA.bvar_inv h_orig)
              (by
                simp [LExpr.liftBVars, hc]
                constructor
                simpa using HasTypeA.bvar_inv h_lifted)
  | app m fn arg ihf iha =>
    simp only [LExpr.liftBVars] at h_lifted ⊢
    obtain ⟨a, hf, ha⟩ := HasTypeA.app_inv h_orig
    obtain ⟨b, hf', ha'⟩ := HasTypeA.app_inv h_lifted
    have h := LExpr.HasTypeA_to_typeCheck ha'
    rw [← List.append_assoc, liftBVars_typeCheck, LExpr.HasTypeA_to_typeCheck ha] at h
    cases h
    rw [denote_app _ hf' ha' h_lifted, denote_app _ hf ha h_orig,
      ihf hf hf' bv₁, iha ha ha' bv₁]
  | abs m name ty body ih =>
    cases ty with
    | none => rfl
    | some a =>
      simp only [LExpr.liftBVars] at h_lifted ⊢
      obtain ⟨r, he, hb⟩ := HasTypeA.abs_inv h_orig
      obtain ⟨r', he', hb'⟩ := HasTypeA.abs_inv h_lifted
      subst he
      cases he'
      rw [denote_abs _ hb' h_lifted, denote_abs _ hb h_orig]
      funext x
      exact ih hb hb' (.cons x bv₁)
  | ite m c t e ihc iht ihe =>
    simp only [LExpr.liftBVars] at h_lifted ⊢
    obtain ⟨hc, ht, he⟩ := HasTypeA.ite_inv h_orig
    obtain ⟨hc', ht', he'⟩ := HasTypeA.ite_inv h_lifted
    rw [denote_ite _ hc' ht' he' h_lifted, denote_ite _ hc ht he h_orig,
      ihc hc hc' bv₁, iht ht ht' bv₁, ihe he he' bv₁]
  | eq m e1 e2 ih1 ih2 =>
    simp only [LExpr.liftBVars] at h_lifted ⊢
    rcases hl : HasTypeA.eq_inv h_lifted with ⟨b, he', h1', h2'⟩
    rcases ho : HasTypeA.eq_inv h_orig with ⟨a, he, h1, h2⟩
    subst he
    have h := LExpr.HasTypeA_to_typeCheck h1'
    rw [← List.append_assoc, liftBVars_typeCheck, LExpr.HasTypeA_to_typeCheck h1] at h
    cases h
    unfold LExpr.denote
    simp only [hl, ho]
    rw [ih1 h1 h1' bv₁, ih2 h2 h2' bv₁]
  | quant m qk name ty tr body iht ih =>
    cases ty with
    | none => rfl
    | some a =>
      simp only [LExpr.liftBVars] at h_lifted ⊢
      obtain ⟨_, he, ht, hb⟩ := HasTypeA.quant_inv h_orig
      obtain ⟨_, he', ht', hb'⟩ := HasTypeA.quant_inv h_lifted
      subst he
      exact denote_quant_congr hb' hb h_lifted h_orig fun x => ih hb hb' (.cons x bv₁)
