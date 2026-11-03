theorem putnam_2019_a1
: {n : ℤ | ∃ A B C : ℤ, A ≥ 0 ∧ B ≥ 0 ∧ C ≥ 0 ∧ A^3 + B^3 + C^3 - 3*A*B*C = n} = (({n : ℤ | n ≥ 0 ∧ ¬Int.ModEq 9 n 3 ∧ ¬Int.ModEq 9 n 6}) : Set ℤ ) := by
  ext n
  constructor
  · rintro ⟨a, b, c, ha, hb, hc, rfl⟩
    refine ⟨?_, ?_⟩
    · nlinarith only [show 0 ≤ (a+b+c)*((a-b)^2 + (b-c)^2 + (c-a)^2) by positivity]
    · change ¬Int.ModEq (9 : ℕ) _ _ ∧ ¬Int.ModEq (9 : ℕ) _ _
      simp_rw [← ZMod.intCast_eq_intCast_iff]
      push_cast
      generalize (a : ZMod 9) = x, (b : ZMod 9) = y, (c : ZMod 9) = z
      decide +revert
  · rintro ⟨hn, h3, h6⟩
    change n % 9 ≠ _ at h3 h6
    obtain rfl | hn := hn.eq_or_lt
    · exact ⟨0, 0, 0, by decide⟩
    · by_cases hr : n % 3 = 0
      case' pos => use n/9+1, n/9, n/9-1
      case' neg =>
        rcases (show n%3=1 ∨ n%3=2 by omega) with h | h <;>
          use n/3+1, n/3+n%3-1, n/3 <;>
          simp only [h]
      all_goals ring_nf <;> omega
