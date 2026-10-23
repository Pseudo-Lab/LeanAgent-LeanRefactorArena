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
      ("axioms", toJson (axioms.toList.map Name.toString))]
    logInfo m!"REFACTOR_EVAL {tag.getString} {report.compress}"


set_option maxHeartbeats 0

open Set Function


set_option Elab.async false in
#refactor_eval "7dc8dbdea2ec49aba0b25c03417e7410" "putnam_1964_a4"
theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  obtain ⟨B, T, hB⟩ := boundedu
  let f n (k : Fin 4) : Icc B T := ⟨u (n+k), hB _⟩
  obtain ⟨a, b, hab, he⟩ := Set.finite_univ.exists_lt_map_eq_of_forall_mem
    (f := f) (by simp)
  have hp m : u (a + m) = u (b + m) := by
    induction m using Nat.strong_induction_on with
    | h m ih =>
      by_cases hm : m < 4
      · exact congrArg Subtype.val (congrFun he ⟨m, hm⟩)
      · apply @Int.cast_injective ℝ
        rw [(hu (a+m) (by omega)).1, (hu (b+m) (by omega)).1]
        simp (disch := omega) only [Nat.add_sub_assoc, ih]
  refine ⟨a, b-a, Nat.sub_pos_of_lt hab, fun n hn => ?_⟩
  convert (hp (n-a)).symm using 2 <;> omega

