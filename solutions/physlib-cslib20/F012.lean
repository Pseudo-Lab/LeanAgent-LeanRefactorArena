lemma isPhenoClosedQ5_viableCharges : (I : CodimensionOneConfig) →
    IsPhenoClosedQ5 I.allowedBarFiveCharges (viableCharges I) := by
  intro i
  apply isPhenClosedQ5_of_isPhenoConstrainedQ5
  cases i <;> decide +kernel
