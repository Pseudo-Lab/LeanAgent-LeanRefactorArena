theorem putnam_2001_b1
  (n : ℕ)
  (hn : n > 0) (hn' : Even n)
  (nums : Fin n → Fin n → ℤ)
  (colors : Fin n → Fin n → Fin 2)
  (hnums : ∀ k l, nums k l = k * n + l + 1)
  (hcolorsrows : ∀ k, (∑ l, (if (colors k l = 0) then 1 else 0)) = n / 2)
  (hcolorscols : ∀ l, (∑ k, (if (colors k l = 0) then 1 else 0)) = n / 2) :
  (∑ k, ∑ l, (if (colors k l = 0) then (nums k l) else 0)) = (∑ k, ∑ l, (if (colors k l = 1) then (nums k l) else 0)) := by
  let w := fun k l => (2 * ((if colors k l = 0 then 1 else 0 : ℕ) : ℤ) - 1)
  have balance (f : Fin n → ℕ) (hf : (∑ i, f i) = n / 2) :
      (∑ i, (2 * (f i : ℤ) - 1)) = 0 := by
    simp only [Finset.sum_sub_distrib, ← Finset.mul_sum, ← Nat.cast_sum, hf,
      Finset.sum_const, Finset.card_univ, Fintype.card_fin, nsmul_eq_mul, mul_one,
      sub_eq_zero]
    exact_mod_cast Nat.mul_div_cancel' hn'.two_dvd
  apply sub_eq_zero.mp
  calc
    _ = ∑ k, ∑ l, w k l * nums k l := by
      simp only [← Finset.sum_sub_distrib]
      refine Finset.sum_congr rfl fun k _ => Finset.sum_congr rfl fun l _ => ?_
      dsimp only [w]
      generalize colors k l = c
      fin_cases c <;> simp
    _ = 0 := by
      simp only [hnums, add_assoc, mul_add, Finset.sum_add_distrib,
        ← Finset.sum_mul, w, balance, hcolorsrows, zero_mul,
        Finset.sum_const_zero, add_zero, zero_add]
      rw [Finset.sum_comm]
      simp only [← Finset.sum_mul, balance, hcolorscols, zero_mul, Finset.sum_const_zero]
