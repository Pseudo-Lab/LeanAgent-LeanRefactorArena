lemma isPhenoClosedQ10_viableCharges : (I : CodimensionOneConfig) →
    IsPhenoClosedQ10 I.allowedTenCharges (viableCharges I) := by
  intro I
  apply isPhenClosedQ10_of_isPhenoConstrainedQ10
  cases I <;> decide +kernel
