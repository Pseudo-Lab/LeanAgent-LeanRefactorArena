lemma isPhenoClosedQ10_viableCharges : (I : CodimensionOneConfig) →
    IsPhenoClosedQ10 I.allowedTenCharges (viableCharges I) := by
  intro i
  apply isPhenClosedQ10_of_isPhenoConstrainedQ10
  cases i <;> decide +kernel
