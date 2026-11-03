theorem putnam_2007_a1
    (P : (ℝ → ℝ) → Prop)
    (P_def : ∀ f, P f ↔ ∃ x y, f x = y ∧ f y = x ∧ deriv f x * deriv f y = 1)
    (α : ℝ) :
    P (fun t ↦ α * t ^ 2 + α * t + 1 / 24) ↔ α ∈ (({2 / 3, 3 / 2, (13 + √601) / 12, (13 - √601) / 12}) : Set ℝ )  := by
  have hd (x : ℝ) : deriv (fun t : ℝ => α*t^2+α*t+1/24) x = 2*α*x+α := by
    convert ((((hasDerivAt_pow 2 x).const_mul α).add
      ((hasDerivAt_id x).const_mul α)).add_const (1/24)).deriv using 1 <;> ring
  rw [P_def]
  simp only [hd, Set.mem_insert_iff, Set.mem_singleton_iff]
  have hs : (Real.sqrt 601)^2 = 601 := Real.sq_sqrt (by norm_num)
  have back (hp : 6*α^2-13*α-18=0) :
      ∃ x y : ℝ, α*x^2+α*x+1/24=y ∧ α*y^2+α*y+1/24=x ∧
        (2*α*x+α)*(2*α*y+α)=1 := by
    have ha : α ≠ 0 := by intro hh; subst α; norm_num at hp
    let x := (-1-α)/(2*α)
    have hx : α*x^2+α*x+1/24=x := by
      dsimp [x]
      field_simp [ha]
      nlinarith only [hp]
    refine ⟨x,x,hx,hx,?_⟩
    dsimp [x]
    field_simp [ha]
    <;> ring
  constructor
  · rintro ⟨x,y,hx,hy,hprod⟩
    have ha : α ≠ 0 := by intro hh; subst α; norm_num at hprod
    have hxy : x=y := by
      by_contra hn
      have hf : (x-y)*(α*(x+y+1)+1)=0 := by linear_combination hx-hy
      have hf' := (mul_eq_zero.mp hf).resolve_left (sub_ne_zero.mpr hn)
      have hz : (2*α*x+α)+(2*α*y+α)=-2 := by linear_combination 2*hf'
      have hsame : 2*α*x+α=2*α*y+α := by
        nlinarith only [hprod, sq_nonneg ((2*α*x+α)-(2*α*y+α)), hz, sq_nonneg ((2*α*x+α)+1)]
      apply hn
      apply mul_left_cancel₀ (mul_ne_zero (by norm_num : (2:ℝ)≠0) ha)
      linarith only [hsame]
    rw [← hxy] at hx hprod
    rcases mul_self_eq_one_iff.mp hprod with hz | hz
    · have hp : 6*α^2-13*α+6=0 := by
        linear_combination 6*(2*α*x+α-1)*hz -24*α*hx
      have hf : (α-2/3)*(α-3/2)=0 := by nlinarith only [hp]
      rcases mul_eq_zero.mp hf with hh | hh
      · exact Or.inl (by linarith only [hh])
      · exact Or.inr (Or.inl (by linarith only [hh]))
    · have hp : 6*α^2-13*α-18=0 := by
        linear_combination 6*(2*α*x+α-3)*hz -24*α*hx
      have hf : (α-(13+Real.sqrt 601)/12)*(α-(13-Real.sqrt 601)/12)=0 := by
        nlinarith only [hp,hs]
      rcases mul_eq_zero.mp hf with hh | hh
      · exact Or.inr (Or.inr (Or.inl (by linarith only [hh])))
      · exact Or.inr (Or.inr (Or.inr (by linarith only [hh])))
  · rintro (hh | hh | hh | hh)
    · subst α; exact ⟨1/4,1/4,by norm_num,by norm_num,by norm_num⟩
    · subst α; exact ⟨-1/6,-1/6,by norm_num,by norm_num,by norm_num⟩
    · apply back; rw [hh]; nlinarith only [hs]
    · apply back; rw [hh]; nlinarith only [hs]
