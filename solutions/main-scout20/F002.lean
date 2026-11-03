theorem denote_suffix_irrel
    {e : LExpr T.mono} {τ : LMonoTy}
    {Δ₁ : List LMonoTy} {Δ₂ Δ₂' : List LMonoTy}
    (h_lc : LExpr.lcAt Δ₁.length e = true)
    (h₁ : LExpr.HasTypeA (Δ₁ ++ Δ₂) e τ)
    (h₂ : LExpr.HasTypeA (Δ₁ ++ Δ₂') e τ)
    (bv₁ : BVarVal tcInterp vt Δ₁)
    (bv₂ : BVarVal tcInterp vt Δ₂)
    (bv₂' : BVarVal tcInterp vt Δ₂')
    : LExpr.denote tcInterp opInterp fvarVal vt (HList.append bv₁ bv₂) e τ h₁ =
      LExpr.denote tcInterp opInterp fvarVal vt (HList.append bv₁ bv₂') e τ h₂ := by
  induction e generalizing Δ₁ τ with
  | const => rfl
  | op _ _ ty | fvar _ _ ty =>
    cases ty with
    | none => exact absurd (LExpr.HasTypeA_to_typeCheck h₁) (by simp [LExpr.typeCheck])
    | some => rfl
  | bvar m i =>
    simp [LExpr.lcAt] at h_lc
    have hp : Δ₁[i]? = some τ := by
      have h := HasTypeA.bvar_inv h₁
      rwa [List.getElem?_append_left (by omega)] at h
    exact (HList.get_append_left bv₁ bv₂ i (HasTypeA.bvar_inv h₁) hp).trans
      (HList.get_append_left bv₁ bv₂' i (HasTypeA.bvar_inv h₂) hp).symm
  | app _ fn arg ih_fn ih_arg =>
    obtain ⟨aty, hf, ha⟩ := HasTypeA.app_inv h₁
    obtain ⟨aty', hf', ha'⟩ := HasTypeA.app_inv h₂
    simp only [LExpr.lcAt, Bool.and_eq_true] at h_lc
    have ht := typeCheck_of_lcAt_aux (Δ := Δ₁ ++ Δ₂) (Δ' := Δ₁ ++ Δ₂') h_lc.2
      (fun i hi => by rw [List.getElem?_append_left hi, List.getElem?_append_left hi])
    rw [LExpr.HasTypeA_to_typeCheck ha, LExpr.HasTypeA_to_typeCheck ha'] at ht
    cases Option.some.inj ht
    rw [denote_app _ hf ha h₁, denote_app _ hf' ha' h₂,
      ih_fn h_lc.1 hf hf' bv₁, ih_arg h_lc.2 ha ha' bv₁]
  | ite _ c t e ih_c ih_t ih_e =>
    obtain ⟨hc, ht, he⟩ := HasTypeA.ite_inv h₁
    obtain ⟨hc', ht', he'⟩ := HasTypeA.ite_inv h₂
    simp only [LExpr.lcAt, Bool.and_eq_true] at h_lc
    rw [denote_ite _ hc ht he, denote_ite _ hc' ht' he',
      ih_c h_lc.1.1 hc hc' bv₁, ih_t h_lc.1.2 ht ht' bv₁, ih_e h_lc.2 he he' bv₁]
  | eq _ e1 e2 ih1 ih2 =>
    obtain ⟨ty, hb, ha, hc⟩ := HasTypeA.eq_inv h₁
    obtain ⟨ty', hb', ha', hc'⟩ := HasTypeA.eq_inv h₂
    subst hb; cases hb'
    simp only [LExpr.lcAt, Bool.and_eq_true] at h_lc
    have ht := typeCheck_of_lcAt_aux (Δ := Δ₁ ++ Δ₂) (Δ' := Δ₁ ++ Δ₂') h_lc.1
      (fun i hi => by rw [List.getElem?_append_left hi, List.getElem?_append_left hi])
    rw [LExpr.HasTypeA_to_typeCheck ha, LExpr.HasTypeA_to_typeCheck ha'] at ht
    cases Option.some.inj ht
    have hleft := ih1 h_lc.1 ha ha' bv₁
    have hright := ih2 h_lc.2 hc hc' bv₁
    by_cases hv : LExpr.denote tcInterp opInterp fvarVal vt (HList.append bv₁ bv₂) e1 ty ha =
        LExpr.denote tcInterp opInterp fvarVal vt (HList.append bv₁ bv₂) e2 ty hc
    · rw [denote_eq_true _ ha hc h₁ hv,
        denote_eq_true _ ha' hc' h₂ (by rwa [← hleft, ← hright])]
    · rw [denote_eq_false _ ha hc h₁ hv,
        denote_eq_false _ ha' hc' h₂ (by rwa [← hleft, ← hright])]
  | abs _ _ ty body ih =>
    cases ty with
    | none => exact absurd (LExpr.HasTypeA_to_typeCheck h₁) (by simp [LExpr.typeCheck])
    | some aty =>
      obtain ⟨_, he, hb⟩ := HasTypeA.abs_inv h₁
      obtain ⟨_, he', hb'⟩ := HasTypeA.abs_inv h₂
      subst he; cases he'
      rw [denote_abs _ hb h₁, denote_abs _ hb' h₂]
      funext x
      exact ih (by simpa [LExpr.lcAt] using h_lc) hb hb' (.cons x bv₁)
  | quant _ qk _ ty tr body ih_tr ih =>
    cases ty with
    | none => exact absurd (LExpr.HasTypeA_to_typeCheck h₁) (by simp [LExpr.typeCheck])
    | some qty =>
      simp only [LExpr.lcAt, Bool.and_eq_true] at h_lc
      obtain ⟨_, he, _, hb⟩ := HasTypeA.quant_inv h₁
      obtain ⟨_, he', _, hb'⟩ := HasTypeA.quant_inv h₂
      subst he; cases he'
      exact denote_quant_congr hb hb' h₁ h₂ fun x =>
        ih (by simpa using h_lc.2) hb hb' (.cons x bv₁)
