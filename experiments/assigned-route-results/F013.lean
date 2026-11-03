lemma isPhenoClosedQ10_viableCharges : (I : CodimensionOneConfig) →
    IsPhenoClosedQ10 I.allowedTenCharges (viableCharges I) := by
  delta IsPhenoClosedQ10
  decide +kernel