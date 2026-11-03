theorem putnam_1995_a3
(relation : (Fin 9 → ℤ) → (Fin 9 → ℤ) → Prop)
(digits_to_num : (Fin 9 → ℤ) → ℤ)
(hdigits_to_num : digits_to_num = fun dig => ∑ i : Fin 9, (dig i) * 10^i.1)
(hrelation : ∀ d e : (Fin 9 → ℤ), relation d e ↔ (∀ i : Fin 9, d i < 10 ∧ d i ≥ 0 ∧ e i < 10 ∧ e i ≥ 0) ∧ (∀ i : Fin 9, 7 ∣ (digits_to_num (fun j : Fin 9 => if j = i then e j else d j))))
: ∀ d e f : (Fin 9 → ℤ), ((relation d e) ∧ (relation e f)) → (∀ i : Fin 9, 7 ∣ d i - f i) := by
  intro d e f h
  have change_digit (d e : Fin 9 → ℤ) (i : Fin 9) :
      digits_to_num (fun j => if j = i then e j else d j) =
        digits_to_num d + (e i - d i) * 10 ^ (i : ℕ) := by
    simp only [hdigits_to_num]
    calc
      (∑ j : Fin 9, (if j = i then e j else d j) * 10 ^ (j : ℕ)) =
          ∑ j : Fin 9, (d j * 10 ^ (j : ℕ) +
            if j = i then (e i - d i) * 10 ^ (i : ℕ) else 0) := by
        apply Finset.sum_congr rfl
        intro j _
        by_cases hj : j = i
        · subst j; simp; ring
        · simp [hj]
      _ = _ := by rw [Finset.sum_add_distrib]; simp
  have hd := ((hrelation d e).mp h.1).2
  have he := ((hrelation e f).mp h.2).2
  simp only [change_digit] at hd he
  have hsum := Finset.dvd_sum (s := Finset.univ) (fun i _ => hd i)
  have h₇ : 7 ∣ digits_to_num e + digits_to_num d := by
    convert dvd_sub hsum (dvd_mul_right (7 : ℤ) (digits_to_num d)) using 1
    simp [hdigits_to_num, sub_mul, Finset.sum_add_distrib, Finset.sum_sub_distrib]
    ring
  intro i
  have hmul : 7 ∣ (f i - d i) * (10 : ℤ) ^ (i : ℕ) := by
    have hh := dvd_sub (dvd_add (he i) (hd i)) h₇
    convert hh using 1 <;> ring
  have hp : Prime (7 : ℤ) := by norm_num
  have hn : ¬ (7 : ℤ) ∣ (10 : ℤ) ^ (i : ℕ) := by
    intro hc
    have hh := hp.dvd_of_dvd_pow hc
    norm_num at hh
  have hh := (hp.dvd_mul.mp hmul).resolve_right hn
  simpa only [neg_sub] using dvd_neg.mpr hh
