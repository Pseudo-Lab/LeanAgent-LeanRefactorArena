theorem putnam_2019_a1
: {n : ℤ | ∃ A B C : ℤ, A ≥ 0 ∧ B ≥ 0 ∧ C ≥ 0 ∧ A^3 + B^3 + C^3 - 3*A*B*C = n} = (({n : ℤ | n ≥ 0 ∧ ¬Int.ModEq 9 n 3 ∧ ¬Int.ModEq 9 n 6}) : Set ℤ ) := by
  have hmod : ∀ a b c : ZMod 9,
      a^3 + b^3 + c^3 - 3*a*b*c ≠ 3 ∧
      a^3 + b^3 + c^3 - 3*a*b*c ≠ 6 := by decide +kernel
  ext n
  constructor
  · rintro ⟨A, B, C, hA, hB, hC, hn⟩
    have hpos : 0 ≤ (A+B+C) * ((A-B)^2 + (B-C)^2 + (C-A)^2) :=
      mul_nonneg (by omega) (by positivity)
    refine ⟨by nlinarith only [hpos, hn], ?_⟩
    apply (and_congr (not_congr (ZMod.intCast_eq_intCast_iff n 3 9))
      (not_congr (ZMod.intCast_eq_intCast_iff n 6 9))).mp
    simpa [← hn] using hmod A B C
  · rintro ⟨hn, h3, h6⟩
    change n % 9 ≠ 3 at h3
    change n % 9 ≠ 6 at h6
    have cases3 : n % 3 = 0 ∨ n % 3 = 1 ∨ n % 3 = 2 := by omega
    rcases cases3 with h | h | h
    · have hn9 : n = 9 * (n / 9) := by omega
      by_cases hz : n = 0
      · subst n
        exact ⟨0, 0, 0, by norm_num⟩
      · refine ⟨n/9+1, n/9, n/9-1, by omega, by omega, by omega, ?_⟩
        nlinarith only [hn9]
    · have he : n = 3 * (n/3) + 1 := by omega
      refine ⟨n/3+1, n/3, n/3, by omega, by omega, by omega, ?_⟩
      nlinarith only [he]
    · have he : n = 3 * (n/3) + 2 := by omega
      refine ⟨n/3+1, n/3+1, n/3, by omega, by omega, by omega, ?_⟩
      nlinarith only [he]
