theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  classical
  obtain ⟨B, T, hB⟩ := boundedu
  let f : ℕ → ℤ × ℤ × ℤ × ℤ := fun n => (u n, u (n+1), u (n+2), u (n+3))
  have hf : Set.Finite (Set.range f) := by
    apply (Set.finite_Icc (B,B,B,B) (T,T,T,T)).subset
    rintro x ⟨n, rfl⟩
    simp only [Set.mem_Icc, Prod.le_def]
    constructor <;> refine ⟨?_,?_,?_,?_⟩ <;>
      first | exact (hB _).1 | exact (hB _).2
  have collision : ∃ i j, i < j ∧ f i = f j := by
    by_contra! h
    apply Set.not_infinite.mpr hf
    apply Set.infinite_range_of_injective
    intro i j he
    by_contra hne
    rcases lt_or_gt_of_ne hne with hij | hij
    · exact h i j hij he
    · exact h j i hij he.symm
  obtain ⟨i,j,hij,he⟩ := collision
  have step (n : ℕ) := (hu (n+4) (by omega)).1
  simp [Nat.add_sub_assoc] at step
  have advance (a b : ℕ) (h : f a = f b) : f (a+1) = f (b+1) := by
    simp only [f, Prod.mk.injEq] at h ⊢
    refine ⟨h.2.1,h.2.2.1,h.2.2.2,?_⟩
    apply Int.cast_injective (α := ℝ)
    rw [step a,step b,h.1,h.2.1,h.2.2.1,h.2.2.2]
  have all (m : ℕ) : f (i+m) = f (j+m) := by
    induction m with
    | zero => exact he
    | succ m ih => exact advance (i+m) (j+m) ih
  refine ⟨i,j-i,by omega,?_⟩
  intro n hn
  simpa only [f, show i+(n-i)=n by omega,
    show j+(n-i)=n+(j-i) by omega] using (congrArg Prod.fst (all (n-i))).symm
