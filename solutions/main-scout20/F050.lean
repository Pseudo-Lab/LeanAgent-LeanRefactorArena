theorem cechCount : Module.finrank ℂ (RS.Cech.H1 (0 : RS.Divisor X)) ≤ genus X := by
  classical
  change RS.Finiteness.h1 (0 : RS.Divisor X) ≤ _
  by_contra
  let P := Classical.arbitrary X
  let n : ℤ := 2 * RS.Finiteness.h1 (0 : RS.Divisor X)
  let D : RS.Divisor X := Function.locallyFinsuppWithin.single P n
  let E : RS.Divisor X := Function.locallyFinsuppWithin.single P (2 * n)
  have : (RS.Finiteness.h1 D : ℤ) = _ := h1_single_eq P (by omega)
  have : (RS.Finiteness.h1 E : ℤ) = _ := h1_single_eq P (by omega)
  have : (RS.l D : ℤ) = _ := l_single_eq P (by omega)
  obtain ⟨ξ, hξ⟩ := Module.finrank_pos_iff_exists_ne_zero.mp
    (by omega : 0 < RS.Finiteness.h1 D)
  have hb (q : RS.LinSys D) : RS.Cech.MulBound q D E :=
    RS.Cech.mulBound_of_mem_linSys q.2 (fun x => by
      simp only [D, E, Function.locallyFinsuppWithin.single_apply]
      split_ifs <;> omega)
  let Φ : RS.LinSys D →ₗ[ℂ] RS.Cech.H1 E :=
    { toFun q := RS.Cech.mulH1 (q : ℳ X) (hb q) ξ
      map_add' _ _ := RS.Cech.mulH1_add _ _ _ _
      map_smul' _ _ := RS.Cech.mulH1_smul _ _ _ _ }
  have : RS.l D ≤ RS.Finiteness.h1 E :=
    LinearMap.finrank_le_finrank_of_injective ((injective_iff_map_eq_zero Φ).mpr (by
      intro q hq
      by_contra hq0
      exact hξ ((map_eq_zero_iff _ ((LinearMap.injective_iff_surjective_of_finrank_eq_finrank
        (by omega : RS.Finiteness.h1 D = RS.Finiteness.h1 E)).mpr
        (RS.Cech.mulH1_surjective (fun h => hq0 (Subtype.ext h)) (hb q)))).mp hq)))
  omega
