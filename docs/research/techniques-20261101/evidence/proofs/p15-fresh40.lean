theorem putnam_1995_a3
(relation : (Fin 9 → ℤ) → (Fin 9 → ℤ) → Prop)
(digits_to_num : (Fin 9 → ℤ) → ℤ)
(hdigits_to_num : digits_to_num = fun dig => ∑ i : Fin 9, (dig i) * 10^i.1)
(hrelation : ∀ d e : (Fin 9 → ℤ), relation d e ↔ (∀ i : Fin 9, d i < 10 ∧ d i ≥ 0 ∧ e i < 10 ∧ e i ≥ 0) ∧ (∀ i : Fin 9, 7 ∣ (digits_to_num (fun j : Fin 9 => if j = i then e j else d j))))
: ∀ d e f : (Fin 9 → ℤ), ((relation d e) ∧ (relation e f)) → (∀ i : Fin 9, 7 ∣ d i - f i) := by
  have q a b (h : relation a b) i :
      7 ∣ b i * 10^i.1 - a i * 10^i.1 + digits_to_num a := by
    convert ((hrelation a b).mp h).2 i using 1
    symm
    rw [hdigits_to_num]
    calc
      _ = ∑ j : Fin 9, ((if j = i then b j * 10^j.1 - a j * 10^j.1 else 0) + a j * 10^j.1) := by
        apply Finset.sum_congr rfl
        intro j _
        simp only [ite_mul, ite_add, sub_add_cancel, zero_add]
      _ = _ := by
        rw [Finset.sum_add_distrib]
        simp only [Finset.sum_ite_eq', Finset.mem_univ, if_true]
  intro d e f h i
  have s := Finset.dvd_sum (s := Finset.univ) (fun j _ => q d e h.1 j)
  simp only [Finset.sum_add_distrib, Finset.sum_sub_distrib,
    ← congrFun hdigits_to_num e, ← congrFun hdigits_to_num d,
    Finset.sum_const, Finset.card_univ, Fintype.card_fin, nsmul_eq_mul] at s
  apply (show IsCoprime (7 : ℤ) (10^i.1) from
    IsCoprime.pow_right ⟨3, -2, rfl⟩).dvd_of_dvd_mul_right
  convert dvd_sub (dvd_sub s (dvd_add (q d e h.1 i) (q e f h.2 i)))
    (dvd_mul_right 7 (digits_to_num d)) using 1 <;> ring1
