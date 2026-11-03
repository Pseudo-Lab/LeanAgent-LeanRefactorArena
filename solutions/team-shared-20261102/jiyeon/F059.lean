theorem putnam_1991_b1
  (m S : ℤ → ℤ)
  (A : ℤ)
  (a : ℕ → ℤ)
  (hm : ∀ n, 0 ≤ n → (m n) ^ 2 ≤ n ∧ (∀ m' : ℤ, m' ^ 2 ≤ n → m' ≤ m n))
  (hS : ∀ n, 0 ≤ n → S n = n - (m n) ^ 2)
  (ha : a 0 = A ∧ (∀ k, a (k + 1) = a k + S (a k)))
  (hA : A > 0) :
  (∃ (K : ℕ) (c : ℕ), ∀ k ≥ K, a k = c) ↔ A ∈ (({A : ℤ | ∃ x > 0, A = x ^ 2}) : Set ℤ ) := by
  have h_nonneg : ∀ k, 0 ≤ a k := by
    intro k
    induction k with
    | zero => simpa [ha.1] using hA.le
    | succ k ih =>
      rw [ha.2 k, hS (a k) ih]
      linarith only [ih, (hm (a k) ih).1]
  have h_S_pos : ∀ (n : ℤ), 0 ≤ n → (∀ (t : ℤ), n ≠ t ^ 2) → S n ≥ 1 := by
    intro n hn hnotsquare
    rw [hS n hn]
    have hb := (hm n hn).1
    have hne := hnotsquare (m n)
    omega
  have h_no_new_squares (k : ℕ) (hk : ∀ t : ℤ, a k ≠ t ^ 2) :
      ∀ t : ℤ, a (k+1) ≠ t ^ 2 := by
    intro t ht
    have hn := h_nonneg k
    obtain ⟨hlo, hmax⟩ := hm (a k) hn
    have hm0 : 0 ≤ m (a k) := hmax 0 (by simpa using hn)
    have hceil : a k < (m (a k) + 1) ^ 2 := by
      by_contra hh
      have hh' := hmax (m (a k) + 1) (le_of_not_gt hh)
      omega
    have heq : t ^ 2 = 2 * a k - m (a k) ^ 2 := by
      rw [ha.2 k, hS (a k) hn] at ht
      linarith only [ht]
    have hstrict : m (a k) ^ 2 < a k := lt_of_le_of_ne hlo (Ne.symm (hk _))
    have hlow : m (a k) < |t| := (sq_lt_sq₀ hm0 (abs_nonneg t)).mp (by
      rw [sq_abs]
      nlinarith only [heq, hstrict])
    have hhigh : |t| < m (a k) + 2 :=
      (sq_lt_sq₀ (abs_nonneg t) (by omega : 0 ≤ m (a k) + 2)).mp (by
        rw [sq_abs]
        nlinarith only [heq, hceil])
    have habs : |t| = m (a k) + 1 := by omega
    have hp : 2 * a k = 2 * m (a k) ^ 2 + 2 * m (a k) + 1 := by
      have hs := sq_abs t
      rw [habs] at hs
      nlinarith only [hs, heq]
    omega
  have h_strict_increasing (hnot : ∀ t : ℤ, A ≠ t ^ 2) (k : ℕ) : a k < a (k+1) := by
    have hn : ∀ k, ∀ t : ℤ, a k ≠ t ^ 2 := by
      intro k
      induction k with
      | zero => simpa [ha.1] using hnot
      | succ k ih => exact h_no_new_squares k ih
    have hp := h_S_pos (a k) (h_nonneg k) (hn k)
    rw [ha.2 k]
    omega
  constructor
  · intro hevent
    by_contra hn
    have hnot : ∀ t : ℤ, A ≠ t ^ 2 := by
      intro t ht
      apply hn
      refine ⟨|t|, ?_, ?_⟩
      · apply abs_pos.mpr
        intro ht0
        subst t
        norm_num at ht
        omega
      · simpa only [sq_abs] using ht
    obtain ⟨K, c, hconst⟩ := hevent
    have hinc := h_strict_increasing hnot K
    linarith [hconst K le_rfl, hconst (K + 1) (Nat.le_succ K)]
  · rintro ⟨x, hx, hx'⟩
    have hS0 : S A = 0 := by
      rw [hS A (le_of_lt hA)]
      have hlo := (hm A (le_of_lt hA)).1
      have hge : x ≤ m A := (hm A (le_of_lt hA)).2 x (le_of_eq hx'.symm)
      nlinarith
    have hconstant (k : ℕ) : a k = A := by
      induction k with
      | zero => exact ha.1
      | succ k ih => rw [ha.2 k, ih, hS0, add_zero]
    refine ⟨0, A.toNat, ?_⟩
    intro k _
    rw [hconstant]
    simp [Int.toNat_of_nonneg (le_of_lt hA)]
