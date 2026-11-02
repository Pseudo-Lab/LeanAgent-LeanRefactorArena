lemma Typing.progress (der : Typing [] t τ) : t.Value ∨ ∃ t', t ⭢βᵛ t' := by
  apply or_iff_not_imp_right.mpr
  generalize eq : [] = Γ at der
  let lc := der.wf.2.1
  induction der <;> subst eq <;> intro hn
  case var mem => simp at mem
  case app l r il ir =>
    have vl := il rfl (fun ⟨_, h⟩ => hn ⟨_, .appₗ r.wf.2.1 h⟩)
    have vr := ir rfl (fun ⟨_, h⟩ => hn ⟨_, .appᵣ vl h⟩)
    obtain ⟨_, _, rfl⟩ := l.canonical_form_abs vl
    exact False.elim (hn ⟨_, .abs vl.lc vr⟩)
  case tapp der sub ih =>
    have v := ih rfl (fun ⟨_, h⟩ => hn ⟨_, .tapp sub.wf.2.1.lc h⟩)
    obtain ⟨_, _, rfl⟩ := der.canonical_form_tabs v
    exact False.elim (hn ⟨_, .tabs v.lc sub.wf.2.1.lc⟩)
  case let' ih _ =>
    have hb := (body_let.mp lc).2
    have v := ih rfl (fun ⟨_, h⟩ => hn ⟨_, .let_bind h hb⟩)
    exact False.elim (hn ⟨_, .let_body v hb⟩)
  case inl ih => exact .inl (ih rfl (fun ⟨_, h⟩ => hn ⟨_, .inl h⟩))
  case inr ih => exact .inr (ih rfl (fun ⟨_, h⟩ => hn ⟨_, .inr h⟩))
  case case der _ _ ih _ _ =>
    obtain ⟨_, hb₂, hb₃⟩ := body_case.mp lc
    have v := ih rfl (fun ⟨_, h⟩ => hn ⟨_, .case h hb₂ hb₃⟩)
    obtain ⟨_, rfl | rfl⟩ := der.canonical_form_sum v
    all_goals cases v
    all_goals apply False.elim; apply hn; solve_by_elim [Exists.intro, Red.case_inl, Red.case_inr]
  all_goals first | constructor; exact lc | rename_i ih; exact ih rfl hn
