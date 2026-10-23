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
#refactor_eval "11fa9667a35046b4bb59afcc8a47023c" "putnam_1964_a4"
theorem putnam_1964_a4
(u : ℕ → ℤ)
(boundedu : ∃ B T : ℤ, ∀ n : ℕ, B ≤ u n ∧ u n ≤ T)
(hu : ∀ n ≥ 4, u n = ((u (n - 1) + u (n - 2) + u (n - 3) * u (n - 4)) : ℝ) / (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ∧ (u (n - 1) * u (n - 2) + u (n - 3) + u (n - 4)) ≠ 0)
: (∃ N c : ℕ, c > 0 ∧ ∀ n ≥ N, u (n + c) = u n) := by
  obtain ⟨B, T, hB⟩ := boundedu
  let f : ℕ → (Fin 4 → Set.Icc B T) := fun n k => ⟨u (n + k), hB (n + k)⟩
  obtain ⟨i, j, hij, he⟩ := Set.finite_univ.exists_lt_map_eq_of_forall_mem
    (f := f) (fun _ => Set.mem_univ _)
  have hp (m : ℕ) : u (i + m) = u (j + m) := by
    induction m using Nat.strong_induction_on with
    | h m ih =>
      by_cases hm : m < 4
      · exact congrArg Subtype.val (congrFun he ⟨m, hm⟩)
      · have hprev (k : ℕ) (hk : 0 < k ∧ k ≤ m) :
            u (i + m - k) = u (j + m - k) := by
          simpa only [Nat.add_sub_assoc hk.2] using ih (m - k) (by omega)
        apply @Int.cast_injective ℝ _ _
        rw [(hu (i + m) (by omega)).1, (hu (j + m) (by omega)).1,
          hprev 1, hprev 2, hprev 3, hprev 4] <;> omega
  refine ⟨i, j - i, by omega, ?_⟩
  intro n hn
  convert (hp (n - i)).symm using 1 <;> congr 1 <;> omega

