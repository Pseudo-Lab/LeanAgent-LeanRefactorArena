theorem buchiFamily_saturation [Inhabited Symbol] :
    Saturates (fun i ↦ (na.buchiFamily i).toSet) (language na).toSet := by
  rintro ⟨a, b⟩ ⟨xs, h_xs, h_lang⟩ ys h_ys
  obtain ⟨xl, xls, h_xl_c, h_xls_c, rfl⟩ := mem_buchiFamily.mp h_xs
  obtain ⟨yl, yls, h_yl_c, h_yls_c, rfl⟩ := mem_buchiFamily.mp h_ys
  obtain ⟨ss, ⟨h_init, h_exec⟩, h_acc⟩ := h_lang
  let f (k : ℕ) := xl.length + xls.cumLen k
  let ts := ωSequence.mk (fun k ↦ ss (f k))
  have (k : ℕ) : xls k ≠ [] := by grind [Language.mem_sub_one]
  have h_xls_p (k : ℕ) : (xls k).length > 0 := List.length_pos_iff.mpr (this k)
  have h_xls_e (k : ℕ) : xls k ∈ na.pairLang (ts k) (ts (k + 1)) := by
    grind [LTS.OmegaExecution.extract_mTr h_exec (?_ : f k ≤ f (k + 1)), LTS.mem_pairLang,
      extract_append_right_right, add_tsub_cancel_left]
  have h_yls (k : ℕ) := buchiCongruence_transfer ((h_xls_c k).left) ((h_yls_c k).left) (h_xls_e k)
  choose sls h_yls_e h_yls_a using h_yls
  have (k : ℕ) : yls k ≠ [] := by grind [Language.mem_sub_one]
  have h_yls_p (k : ℕ) : (yls k).length > 0 := List.length_pos_iff.mpr (this k)
  obtain ⟨ss1, h_ss1_run, h_ss1_seg⟩ := LTS.OmegaExecution.flatten_execution h_yls_e h_yls_p
  suffices ∃ᶠ (k : ℕ) in atTop, ss1 k ∈ na.accept by
    have h_xl_e : xl ∈ na.pairLang (ss 0) (ts 0) := by
      grind [LTS.OmegaExecution.extract_mTr h_exec (?_ : 0 ≤ xl.length),
        extract_append_zero_right, LTS.mem_pairLang]
    have h_yl_e : yl ∈ na.pairLang (ss 0) (ts 0) := by
      grind [buchiCongruence_transfer h_xl_c h_yl_c h_xl_e, LTS.mem_pairLang, LTS.Execution.to_mTr]
    have h_ss1_ts : ss1 0 = ts 0 := by
      have h : 0 < yls.cumLen 1 - yls.cumLen 0 := by grind
      have : sls 0 ≠ [] := by grind
      have : 0 < (sls 0).length := List.length_pos_iff.mpr this
      have : ss1 0 = (sls 0)[0] := by grind [get_extract (xs := ss1) h]
      have : (sls 0)[0] = ts 0 := h_yls_e 0 |>.choose_spec |>.1
      grind
    obtain ⟨ss2, _, _, _, _⟩ := LTS.OmegaExecution.append h_yl_e h_ss1_run h_ss1_ts
    use ss2
    have := @drop_frequently_iff_frequently _ ss2 na.accept yl.length
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
  obtain ⟨_, _, _, _⟩ := h_yls_e m
  obtain ⟨_, _, _, _⟩ := h_yls_e (m + 1)
  grind =>
   have := @get_extract (xs := ss1)
   have : k < (yls m).length ∨ ¬ k < (yls m).length
   have : k < yls.cumLen (m + 1) - yls.cumLen m ∨ 0 < yls.cumLen (m + 2) - yls.cumLen (m + 1)
   finish
