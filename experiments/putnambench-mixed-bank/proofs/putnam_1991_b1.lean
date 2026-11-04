theorem putnam_1991_b1
  (m S : ℤ → ℤ)
  (A : ℤ)
  (a : ℕ → ℤ)
  (hm : ∀ n, 0 ≤ n → (m n) ^ 2 ≤ n ∧ (∀ m' : ℤ, m' ^ 2 ≤ n → m' ≤ m n))
  (hS : ∀ n, 0 ≤ n → S n = n - (m n) ^ 2)
  (ha : a 0 = A ∧ (∀ k, a (k + 1) = a k + S (a k)))
  (hA : A > 0) :
  (∃ (K : ℕ) (c : ℕ), ∀ k ≥ K, a k = c) ↔ A ∈ (({A : ℤ | ∃ x > 0, A = x ^ 2}) : Set ℤ ) := by
  rcases ha with ⟨rfl, ha⟩
  have hn {k} : 0 ≤ a k := by
    induction k with
    | zero => exact hA.le
    | succ k ih =>
      rw [ha k, hS _ ih]
      have := (hm _ ih).1
      omega
  have hz {n} h := (hm n h).2 0 (by simpa using h)
  have descend (k : ℕ) (t : ℤ) (ht : 0 ≤ t) (he : a k = t ^ 2) :
      ∃ s : ℤ, 0 < s ∧ a 0 = s ^ 2 := by
    induction k generalizing t with
    | zero => exact ⟨t, by nlinarith, he⟩
    | succ k ih =>
      obtain ⟨hl, hmax⟩ := hm (a k) hn
      apply ih (m (a k)) (hz hn)
      have hu := mt (hmax (m (a k) + 1)) (by omega)
      rw [ha k, hS _ hn] at he
      by_cases htlow : t ≤ m (a k)
      · nlinarith only [he, hl, htlow, ht]
      · have : t = m (a k) + 1 := by
          clear hA ht
          nlinarith
        subst t
        ring_nf at he
        omega
  constructor
  · rintro ⟨K, c, hc⟩
    have he := hc (K + 1) (by omega)
    rw [ha K, hS _ hn, ← hc K le_rfl] at he
    exact descend K (m (a K)) (hz hn) (by omega)
  · rintro ⟨x, hx, he⟩
    refine ⟨0, (a 0).toNat, ?_⟩
    rintro k -
    rw [Int.toNat_of_nonneg hA.le]
    induction k with
    | zero => rfl
    | succ k ih =>
      rw [ha k, ih, hS (a 0) hA.le]
      nlinarith only [hx, he, (hm (a 0) hA.le).1, (hm (a 0) hA.le).2 x he.ge]
