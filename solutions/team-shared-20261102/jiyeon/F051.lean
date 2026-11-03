theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n)  := by
  classical
  obtain ⟨B, T, hb⟩ := boundedu
  let f : ℕ → ℤ × ℤ × ℤ × ℤ := fun n => (u n, u (n+1), u (n+2), u (n+3))
  have hf : Set.MapsTo f Set.univ (Set.Icc (B,B,B,B) (T,T,T,T)) := by
    intro n _
    exact ⟨⟨(hb n).1, (hb (n+1)).1, (hb (n+2)).1, (hb (n+3)).1⟩,
      ⟨(hb n).2, (hb (n+1)).2, (hb (n+2)).2, (hb (n+3)).2⟩⟩
  obtain ⟨i, _, j, _, hij, heq⟩ :=
    Set.infinite_univ.exists_ne_map_eq_of_mapsTo hf (Set.finite_Icc _ _)
  have hp : ∃ i j, i < j ∧ f i = f j := by
    rcases lt_or_gt_of_ne hij with h | h
    · exact ⟨i,j,h,heq⟩
    · exact ⟨j,i,h,heq.symm⟩
  obtain ⟨i,j,hij,heq⟩ := hp
  simp only [f, Prod.mk.injEq] at heq
  have hs : ∀ m, u (i+m) = u (j+m) := by
    intro m
    induction m using Nat.strong_induction_on with
    | h m ih =>
      by_cases hm : m < 4
      · interval_cases m
        · simpa using heq.1
        · exact heq.2.1
        · exact heq.2.2.1
        · exact heq.2.2.2
      · have hk (k : ℕ) (hk0 : 0 < k) (hk4 : k ≤ 4) :
            u (i+m-k) = u (j+m-k) := by
          simpa only [Nat.add_sub_assoc (by omega : k ≤ m)] using ih (m-k) (by omega)
        apply Int.cast_injective (α := ℝ)
        rw [(hu (i+m) (by omega)).1, (hu (j+m) (by omega)).1,
          hk 1 (by decide) (by decide), hk 2 (by decide) (by decide),
          hk 3 (by decide) (by decide), hk 4 (by decide) (by decide)]
  refine ⟨i,j-i,Nat.sub_pos_of_lt hij,?_⟩
  intro n hn
  convert (hs (n-i)).symm using 1 <;> congr 1 <;> omega
