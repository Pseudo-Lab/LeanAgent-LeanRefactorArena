lemma isPhenoClosedQ5_viableCharges : (I : CodimensionOneConfig) →
    IsPhenoClosedQ5 I.allowedBarFiveCharges (viableCharges I) := by
  intro I
  apply isPhenClosedQ5_of_isPhenoConstrainedQ5
  cases I <;> decide +kernel
