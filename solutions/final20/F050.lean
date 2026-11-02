theorem cechCount : Module.finrank ℂ (RS.Cech.H1 (0 : RS.Divisor X)) ≤ genus X := by
  classical
  let c := RS.Finiteness.h1 (0 : RS.Divisor X)
  change c ≤ genus X
  by_contra! hcon
  let P : X := Classical.arbitrary X
  let D : RS.Divisor X := Function.locallyFinsuppWithin.single P (2 * (c : ℤ))
  let E : RS.Divisor X := Function.locallyFinsuppWithin.single P (4 * (c : ℤ))
  have hd : (RS.Finiteness.h1 D : ℤ) = (c : ℤ) - genus X :=
    h1_single_eq P (by omega)
  have he : (RS.Finiteness.h1 E : ℤ) = (c : ℤ) - genus X :=
    h1_single_eq P (by omega)
  have hl : (RS.l D : ℤ) = 2 * (c : ℤ) + 1 - genus X :=
    l_single_eq P (by omega)
  obtain ⟨ξ, hξ⟩ := Module.finrank_pos_iff_exists_ne_zero.mp
    (show 0 < RS.Finiteness.h1 D by omega)
  have bound (q : RS.LinSys D) : RS.Cech.MulBound q D E :=
    RS.Cech.mulBound_of_mem_linSys q.2 (fun x => by
      simp only [D, E, Function.locallyFinsuppWithin.single_apply]
      split_ifs <;> omega)
  have hh : RS.l D ≤ RS.Finiteness.h1 E :=
    LinearMap.finrank_le_finrank_of_injective (f :=
      { toFun := fun q => RS.Cech.mulH1 _ (bound q) ξ
        map_add' := fun q r => RS.Cech.mulH1_add (bound q) (bound r) (bound (q + r)) ξ
        map_smul' := fun a q => RS.Cech.mulH1_smul a (bound q) (bound (a • q)) ξ }) (by
      refine (injective_iff_map_eq_zero _).mpr fun q hq => ?_
      by_contra hq0
      exact hξ ((map_eq_zero_iff _
        ((LinearMap.injective_iff_surjective_of_finrank_eq_finrank
          (Int.natCast_inj.mp (hd.trans he.symm))).mpr
          (RS.Cech.mulH1_surjective (Subtype.coe_ne_coe.mpr hq0) (bound q)))).mp hq))
  omega
