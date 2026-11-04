theorem putnam_1995_a3
(relation : (Fin 9 → ℤ) → (Fin 9 → ℤ) → Prop)
(digits_to_num : (Fin 9 → ℤ) → ℤ)
(hdigits_to_num : digits_to_num = fun dig => ∑ i : Fin 9, (dig i) * 10^i.1)
(hrelation : ∀ d e : (Fin 9 → ℤ), relation d e ↔ (∀ i : Fin 9, d i < 10 ∧ d i ≥ 0 ∧ e i < 10 ∧ e i ≥ 0) ∧ (∀ i : Fin 9, 7 ∣ (digits_to_num (fun j : Fin 9 => if j = i then e j else d j))))
: ∀ d e f : (Fin 9 → ℤ), ((relation d e) ∧ (relation e f)) → (∀ i : Fin 9, 7 ∣ d i - f i) := by
  classical
  have hnum (d : Fin 9 → ℤ) : (∑ i : Fin 9, d i * 10 ^ i.val) = digits_to_num d :=
    (congrFun hdigits_to_num d).symm
  have upd (d e : Fin 9 → ℤ) (i : Fin 9) :
      digits_to_num (fun j => if j = i then e j else d j) =
        (e i - d i) * 10 ^ i.val + digits_to_num d := by
    rw [hdigits_to_num]
    calc
      _ = ∑ j : Fin 9, ((if j = i then (e i - d i) * 10 ^ i.val else 0) + d j * 10 ^ j.val) := by
        apply Finset.sum_congr rfl
        intro j _
        by_cases hj : j = i
        · subst j
          simp only [ite_true, sub_mul, sub_add_cancel]
        · simp only [hj, if_false, zero_add]
      _ = _ := by
        rw [Finset.sum_add_distrib, Finset.sum_ite_eq', if_pos (Finset.mem_univ i)]
  have hd (d e : Fin 9 → ℤ) (h : relation d e) (i : Fin 9) :
      7 ∣ (e i - d i) * 10 ^ i.val + digits_to_num d := by
    rw [← upd]
    exact ((hrelation d e).mp h).2 i
  intro d e f ⟨hde, hef⟩ i
  have hsum : (7 : ℤ) ∣ ∑ j : Fin 9, ((e j - d j) * 10 ^ j.val + digits_to_num d) :=
    Finset.dvd_sum (fun j _ => hd d e hde j)
  simp only [Finset.sum_add_distrib, sub_mul, Finset.sum_sub_distrib,
    hnum, Finset.sum_const, Finset.card_univ, Fintype.card_fin, nsmul_eq_mul] at hsum
  have hs : 7 ∣ digits_to_num e + digits_to_num d := by
    convert dvd_sub hsum (dvd_mul_right (7 : ℤ) (digits_to_num d)) using 1 <;> ring
  have hw := dvd_sub (dvd_add (hd e f hef i) (hd d e hde i)) hs
  rw [add_add_add_comm, add_sub_cancel_right, ← add_mul, sub_add_sub_cancel] at hw
  have hc : IsCoprime (7 : ℤ) 10 := ⟨3, -2, by decide⟩
  exact dvd_sub_comm.mp (hc.pow_right.dvd_of_dvd_mul_right hw)
