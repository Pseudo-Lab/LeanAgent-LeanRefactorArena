theorem buchiFamily_saturation [Inhabited Symbol] :
    Saturates (fun i ↦ (na.buchiFamily i).toSet) (language na).toSet := by
  rintro ⟨a, b⟩ ⟨xs, h_xs, ⟨ss, ⟨h_init, h_exec⟩, h_acc⟩⟩ ys h_ys
  obtain ⟨xl, xls, h_xl_c, h_xls_c, rfl⟩ := mem_buchiFamily.mp h_xs
  obtain ⟨yl, yls, h_yl_c, h_yls_c, rfl⟩ := mem_buchiFamily.mp h_ys
  let f k := xl.length + xls.cumLen k
  let ts := ωSequence.mk fun k ↦ ss (f k)
  have h_yl_e := LTS.Execution.to_mTr
    (buchiCongruence_transfer (s := ss 0) (t := ts 0) h_xl_c h_yl_c (by
      grind [LTS.OmegaExecution.extract_mTr h_exec (Nat.zero_le xl.length),
        extract_append_zero_right, LTS.mem_pairLang])).choose_spec.1
  clear h_xl_c h_yl_c
  simp only [Language.mem_sub_one] at h_xls_c h_yls_c
  have h_xls_p k := List.length_pos_iff.mpr (h_xls_c k).2
  have h_yls_p k := List.length_pos_iff.mpr (h_yls_c k).2
  choose sls h_yls_e h_yls_a using fun k ↦
    buchiCongruence_transfer (s := ts k) (t := ts (k + 1))
      (h_xls_c k).left (h_yls_c k).left (by
        clear h_xls_c h_yls_c h_init h_acc h_yls_p h_yl_e
        grind [LTS.OmegaExecution.extract_mTr h_exec (?_ : f k ≤ f (k + 1)),
          LTS.mem_pairLang, extract_append_right_right, add_tsub_cancel_left])
  obtain ⟨ss1, h_ss1_run, h_ss1_seg⟩ := LTS.OmegaExecution.flatten_execution h_yls_e h_yls_p
  clear h_xls_c h_yls_c
  have h_start m : ss1 (yls.cumLen m) = ts m := by
    clear h_xls_p h_acc h_exec h_init h_yls_a h_ss1_run h_yl_e
    specialize h_yls_e m
    specialize h_ss1_seg m
    have h := Nat.sub_pos_of_lt (cumLen_strictMono h_yls_p (Nat.lt_succ_self m))
    clear h_yls_p
    have : 0 < (sls m).length := by grind
    have := h_yls_e.choose_spec.1
    grind [get_extract (xs := ss1) h]
  suffices ∃ᶠ k in atTop, ss1 k ∈ na.accept by
    obtain ⟨ss2, h2⟩ := LTS.OmegaExecution.append h_yl_e h_ss1_run (by simpa using h_start 0)
    use ss2
    have := @drop_frequently_iff_frequently _ ss2 na.accept yl.length
    clear h_xls_p h_yls_p h_yls_e h_yls_a h_ss1_seg h_exec h_acc h_start
    grind [Run.mk]
  apply frequently_atTop.mpr
  intro n
  obtain ⟨m, _, s, _, h_mem⟩ :=
    frequently_atTop.mp ((frequently_via_accept h_acc h_exec h_xls_p f rfl ts rfl).mono h_yls_a) n
  obtain ⟨k, _, _⟩ := List.mem_iff_getElem.mp h_mem
  use yls.cumLen m + k
  suffices ss1 (yls.cumLen m + k) = (sls m)[k] by
    have := StrictMono.add_le_nat (cumLen_strictMono h_yls_p) m 0
    lia
  clear h_xls_p h_acc h_exec h_init h_yls_a h_ss1_run h_yl_e
  obtain ⟨_, _, _, _⟩ := h_yls_e m
  by_cases hk : k < (yls m).length
  · specialize h_ss1_seg m
    clear h_yls_p h_yls_e h_start
    have h : k < yls.cumLen (m + 1) - yls.cumLen m := by
      rwa [cumLen_succ, Nat.add_sub_cancel_left]
    grind [get_extract (xs := ss1) h]
  · have := h_start (m + 1)
    clear h_start h_yls_p h_yls_e h_ss1_seg
    grind