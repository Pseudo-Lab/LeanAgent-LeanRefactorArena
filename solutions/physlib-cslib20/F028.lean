theorem OmegaExecution.flatten_execution [Inhabited Label]
    {ts : ωSequence State} {μls : ωSequence (List Label)} {sls : ωSequence (List State)}
    (hexec : ∀ k, lts.Execution (ts k) (μls k) (ts (k + 1)) (sls k))
    (hpos : ∀ k, (μls k).length > 0) :
    ∃ ss, lts.OmegaExecution ss μls.flatten ∧
      ∀ k, ss.extract (μls.cumLen k) (μls.cumLen (k + 1)) = (sls k).take (μls k).length := by
  have : Inhabited State := {default := ts 0}
  let segs := ωSequence.mk fun k ↦ (sls k).take (μls k).length
  have h_len : μls.cumLen = segs.cumLen := by ext k; induction k <;> grind
  have h_pos (k : ℕ) : (segs k).length > 0 := by grind [List.eq_nil_iff_length_eq_zero]
  have h_mono := cumLen_strictMono h_pos
  have h_zero := cumLen_zero (ls := segs)
  have h_seg0 (k : ℕ) : (segs k)[0]! = ts k := by grind
  use segs.flatten
  split_ands
  · intro n
    simp only [h_len, flatten_def]
    simp only [Execution] at hexec
    have := segment_lower_bound h_mono h_zero n
    by_cases h_n : n + 1 < segs.cumLen (segment segs.cumLen n + 1)
    · have := segment_range_val h_mono (by grind) h_n
      have : n + 1 - segs.cumLen (segment segs.cumLen n) < (μls (segment segs.cumLen n)).length :=
        by grind
      grind
    · have h1 : segs.cumLen (segment segs.cumLen n + 1) = n + 1 := by
        grind [segment_upper_bound h_mono h_zero n]
      have h2 : segment segs.cumLen (n + 1) = segment segs.cumLen n + 1 := by
        simp [← h1, segment_idem h_mono]
      have : n + 1 - segs.cumLen (segment segs.cumLen n) = (μls (segment segs.cumLen n)).length :=
        by grind
      have h3 : ts (segment segs.cumLen n + 1) =
          (sls (segment segs.cumLen n))[n + 1 - segs.cumLen (segment segs.cumLen n)]! := by
        grind
      simp [h1, h2, h_seg0, h3]
      grind
  · simp [h_len, extract_flatten h_pos, segs]
