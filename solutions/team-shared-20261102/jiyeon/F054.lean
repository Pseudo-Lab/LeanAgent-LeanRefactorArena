theorem putnam_2001_b1
  (n : ℕ)
  (hn : n > 0) (hn' : Even n)
  (nums : Fin n → Fin n → ℤ)
  (colors : Fin n → Fin n → Fin 2)
  (hnums : ∀ k l, nums k l = k * n + l + 1)
  (hcolorsrows : ∀ k, (∑ l, (if (colors k l = 0) then 1 else 0)) = n / 2)
  (hcolorscols : ∀ l, (∑ k, (if (colors k l = 0) then 1 else 0)) = n / 2) :
  (∑ k, ∑ l, (if (colors k l = 0) then (nums k l) else 0)) = (∑ k, ∑ l, (if (colors k l = 1) then (nums k l) else 0)) := by
  have hb (g : Fin n → Fin 2) (hc : (∑ j, if g j=0 then 1 else 0) = n/2) :
      (∑ j, (2*(if g j=0 then (1:ℤ) else 0)-1)) = 0 := by
    have hh : (∑ j, if g j=0 then (1:ℤ) else 0) = (n/2 : ℕ) := by exact_mod_cast hc
    have he : (2:ℤ) * (n/2 : ℕ) = n := by
      exact_mod_cast Nat.mul_div_cancel' (even_iff_two_dvd.mp hn')
    rw [Finset.sum_sub_distrib, ← Finset.mul_sum, hh]
    simpa only [Finset.sum_const, Finset.card_univ, Fintype.card_fin, nsmul_eq_mul,
      mul_one, he, sub_self]
  have hrow_sum_zero (k : Fin n) :
      (∑ l, (2*(if colors k l=0 then (1:ℤ) else 0)-1)) = 0 := hb (colors k) (hcolorsrows k)
  have hcol_sum_zero (l : Fin n) :
      (∑ k, (2*(if colors k l=0 then (1:ℤ) else 0)-1)) = 0 :=
    hb (fun k => colors k l) (hcolorscols l)
  apply sub_eq_zero.mp
  calc
    _ = ∑ k : Fin n, ∑ l : Fin n,
        (2*(if colors k l=0 then (1:ℤ) else 0)-1)*nums k l := by
      simp only [← Finset.sum_sub_distrib]
      apply Finset.sum_congr rfl
      intro k _
      apply Finset.sum_congr rfl
      intro l _
      rcases (show colors k l = 0 ∨ colors k l = 1 by omega) with h | h <;> simp [h]
    _ = 0 := by
      simp_rw [hnums, mul_add, Finset.sum_add_distrib]
      simp_rw [← Finset.sum_mul, hrow_sum_zero, zero_mul, Finset.sum_const_zero, zero_add]
      rw [Finset.sum_comm]
      simp_rw [← Finset.sum_mul, hcol_sum_zero, zero_mul]
      simp
