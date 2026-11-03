theorem OmegaExecution.flatten_execution [Inhabited Label]
    {ts : ωSequence State} {μls : ωSequence (List Label)} {sls : ωSequence (List State)}
    (hexec : ∀ k, lts.Execution (ts k) (μls k) (ts (k + 1)) (sls k))
    (hpos : ∀ k, (μls k).length > 0) :
    ∃ ss, lts.OmegaExecution ss μls.flatten ∧
      ∀ k, ss.extract (μls.cumLen k) (μls.cumLen (k + 1)) = (sls k).take (μls k).length := by
  have : Inhabited State := ⟨ts 0⟩
  let segs := ωSequence.mk fun k ↦ (sls k).take (μls k).length
  have h_len : μls.cumLen = segs.cumLen := by ext k; induction k <;> grind
  have h_pos k : (segs k).length > 0 := by
    specialize hexec k
    grind
  have h_mono := cumLen_strictMono h_pos
  have h_seg0 k : (segs k)[0]! = ts k := by
    specialize hexec k
    grind
  use segs.flatten
  constructor
  · intro n
    simp only [h_len, flatten_def]
    specialize hexec (segment segs.cumLen n)
    have := segment_lower_bound h_mono cumLen_zero n
    clear h_pos
    rcases lt_or_eq_of_le (Nat.add_one_le_iff.mpr (segment_upper_bound h_mono cumLen_zero n)) with h_n | h1
    · have := segment_range_val h_mono (by omega) h_n
      clear h_seg0
      grind
    · have : n + 1 - segs.cumLen (segment segs.cumLen n) = (μls (segment segs.cumLen n)).length := by
        rw [h1, ← h_len, cumLen_succ, Nat.add_sub_cancel_left]
      simp only [h1, segment_idem h_mono, Nat.sub_self, h_seg0]
      clear h_seg0
      grind
  · simp [h_len, extract_flatten h_pos, segs]