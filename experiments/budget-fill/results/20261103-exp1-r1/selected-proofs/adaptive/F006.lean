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
  induction e generalizing Δ₁ τ <;> simp only [LExpr.liftBVars] at h_lifted ⊢
  case const => rfl
  case op | fvar => cases ‹Option LMonoTy› <;> rfl
  case bvar m i =>
    split <;> rename_i hi <;>
      simp only [hi, ↓reduceIte] at h_lifted <;>
      dsimp only [LExpr.denote]
    · have hx := HasTypeA.bvar_inv h_orig
      rw [List.getElem?_append_right hi] at hx
      have hs := HasTypeA.bvar_inv h_lifted
      rw [List.getElem?_append_right (by omega)] at hs
      have he : i + Δ_insert.length - Δ₁.length - Δ_insert.length = i - Δ₁.length := by omega
      rw [HList.get_append_right bv₁ bv_outer i _ hx hi,
          HList.get_append_right bv₁ _ _ _ hs (by omega),
          HList.get_append_right bv_insert bv_outer _ hs (he.symm ▸ hx) (by omega)]
      simp only [he]
    · have hx := HasTypeA.bvar_inv h_orig
      rw [List.getElem?_append_left (by omega : i < Δ₁.length)] at hx
      simp only [HList.get_append_left bv₁ _ _ _ hx]
  case app m fn arg ihf iha =>
    obtain ⟨a, hf, ha⟩ := HasTypeA.app_inv h_orig
    obtain ⟨b, hfl, hal⟩ := HasTypeA.app_inv h_lifted
    have he := LExpr.HasTypeA_to_typeCheck hfl
    rw [← List.append_assoc, liftBVars_typeCheck, LExpr.HasTypeA_to_typeCheck hf] at he
    cases he
    rw [denote_app _ hfl hal h_lifted, denote_app _ hf ha h_orig,
        ihf hf hfl bv₁, iha ha hal bv₁]
  case abs m name ty body ih =>
    cases ty with
    | none => rfl
    | some a =>
      obtain ⟨r, rfl, hb⟩ := HasTypeA.abs_inv h_orig
      obtain ⟨s, ⟨⟩, hbl⟩ := HasTypeA.abs_inv h_lifted
      rw [denote_abs _ hbl h_lifted, denote_abs _ hb h_orig]
      funext x
      exact ih hb hbl (.cons x bv₁)
  case ite m c t e ihc iht ihe =>
    obtain ⟨hc, ht', he⟩ := HasTypeA.ite_inv h_orig
    obtain ⟨hcl, htl, hel⟩ := HasTypeA.ite_inv h_lifted
    rw [denote_ite _ hcl htl hel h_lifted, denote_ite _ hc ht' he h_orig,
        ihc hc hcl bv₁, iht ht' htl bv₁, ihe he hel bv₁]
  case eq m e1 e2 ih1 ih2 =>
    conv => congr <;> unfold LExpr.denote
    rcases HasTypeA.eq_inv h_lifted with ⟨b, he', h1l, h2l⟩
    rcases HasTypeA.eq_inv h_orig with ⟨a, rfl, h1, h2⟩
    have hab := LExpr.HasTypeA_to_typeCheck h1l
    rw [← List.append_assoc, liftBVars_typeCheck, LExpr.HasTypeA_to_typeCheck h1] at hab
    cases hab
    dsimp only
    rw [ih1 h1 h1l bv₁, ih2 h2 h2l bv₁]
  case quant m q name ty tr body ihtr ih =>
    cases ty with
    | none => rfl
    | some a =>
      obtain ⟨_, rfl, _, hb⟩ := HasTypeA.quant_inv h_orig
      obtain ⟨_, _, _, hbl⟩ := HasTypeA.quant_inv h_lifted
      exact denote_quant_congr hbl hb h_lifted h_orig fun x =>
        ih hb hbl (.cons x bv₁)
