theorem putnam_1995_a3
(relation : (Fin 9 → ℤ) → (Fin 9 → ℤ) → Prop)
(digits_to_num : (Fin 9 → ℤ) → ℤ)
(hdigits_to_num : digits_to_num = fun dig => ∑ i : Fin 9, (dig i) * 10^i.1)
(hrelation : ∀ d e : (Fin 9 → ℤ), relation d e ↔ (∀ i : Fin 9, d i < 10 ∧ d i ≥ 0 ∧ e i < 10 ∧ e i ≥ 0) ∧ (∀ i : Fin 9, 7 ∣ (digits_to_num (fun j : Fin 9 => if j = i then e j else d j))))
: ∀ d e f : (Fin 9 → ℤ), ((relation d e) ∧ (relation e f)) → (∀ i : Fin 9, 7 ∣ d i - f i) := by
  have q a b (h : relation a b) i :
      7 ∣ b i * 10^i.1 + (digits_to_num a - a i * 10^i.1) := by
    simpa only [hdigits_to_num, ite_mul, Finset.sum_ite,
      Finset.filter_eq', Finset.filter_ne', Finset.mem_univ, if_true, Finset.sum_singleton,
      Finset.sum_erase_eq_sub] using ((hrelation a b).mp h).2 i
  intro d e f h i
  have s := Finset.dvd_sum (s := Finset.univ) (fun j _ => q d e h.1 j)
  simp only [Finset.sum_add_distrib, Finset.sum_sub_distrib,
    ← congrFun hdigits_to_num e, ← congrFun hdigits_to_num d,
    Finset.sum_const, Finset.card_univ, Fintype.card_fin, nsmul_eq_mul] at s
  apply ((show IsCoprime (7 : ℤ) 10 from ⟨3, -2, rfl⟩).pow_right).dvd_of_dvd_mul_right
  convert dvd_sub (dvd_sub s (dvd_add (q d e h.1 i) (q e f h.2 i)))
    (dvd_mul_right 7 (digits_to_num d)) using 1 <;> ring1
