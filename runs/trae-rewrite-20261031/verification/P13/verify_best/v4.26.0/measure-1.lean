import Lean
import Mathlib
import Aesop

open Lean Elab Command in
elab "#refactor_eval " tag:str target:str cmd:command : command =>
  show CommandElabM Unit from do
    let name := target.getString.toName
    if (← getEnv).contains name then
      throwError "evaluation target already exists before candidate"
    let start ← IO.getNumHeartbeats
    elabCommand cmd
    let finish ← IO.getNumHeartbeats
    let env ← getEnv
    unless env.contains name do
      throwError "candidate did not define evaluation target"
    let axioms ← Lean.collectAxioms name
    let report := Json.mkObj [
      ("target", toJson target.getString),
      ("raw", toJson (finish - start)),
      ("scaled", toJson ((finish - start) / 1000)),
      ("axioms", toJson (axioms.toList.map Lean.Name.toString))]
    logInfo m!"REFACTOR_EVAL {tag.getString} {report.compress}"


set_option maxHeartbeats 0

open Set Function


set_option Elab.async false in
#refactor_eval "be6073097b9545cd88f4e427bb232418" "putnam_1964_a4"
theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  obtain ⟨B, T, hB⟩ := boundedu
  obtain ⟨i, j, hij, he⟩ := Set.finite_univ.exists_lt_map_eq_of_forall_mem (f := fun n (k : Fin 4) => (⟨u (n + k), hB (n + k)⟩ : Set.Icc B T)) fun _ => Set.mem_univ _
  have hp (m : ℕ) : u (i + m) = u (j + m) := by
    induction m using Nat.strong_induction_on with
    | h m ih =>
      by_cases hm : m < 4
      · exact congrArg Subtype.val $ congrFun he ⟨m, hm⟩
      · have hprev k (hk : 0 < k ∧ k ≤ m) : u (i + m - k) = u (j + m - k) := by simpa only [Nat.add_sub_assoc hk.2] using ih _ $ Nat.sub_lt (by omega) hk.1
        exact Int.cast_injective $ by rw [(hu (i + m) $ by omega).1, (hu (j + m) $ by omega).1, hprev 1, hprev 2, hprev 3, hprev 4] <;> omega
  exact ⟨i, j - i, by omega, fun n hn => by convert (hp (n - i)).symm using 1 <;> congr 1 <;> omega⟩


