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

open Filter Topology Real


set_option Elab.async false in
#refactor_eval "c1632991668a48b48662f05c2b4b9ed1" "putnam_1995_a3"
theorem putnam_1995_a3
(relation : (Fin 9 → ℤ) → (Fin 9 → ℤ) → Prop)
(digits_to_num : (Fin 9 → ℤ) → ℤ)
(hdigits_to_num : digits_to_num = fun dig => ∑ i : Fin 9, (dig i) * 10^i.1)
(hrelation : ∀ d e : (Fin 9 → ℤ), relation d e ↔ (∀ i : Fin 9, d i < 10 ∧ d i ≥ 0 ∧ e i < 10 ∧ e i ≥ 0) ∧ (∀ i : Fin 9, 7 ∣ (digits_to_num (fun j : Fin 9 => if j = i then e j else d j))))
: ∀ d e f : (Fin 9 → ℤ), ((relation d e) ∧ (relation e f)) → (∀ i : Fin 9, 7 ∣ d i - f i) := by
  intro d e f h i
  simp only [hrelation, hdigits_to_num, ite_mul, Finset.sum_ite, Finset.filter_eq', Finset.filter_ne',
    Finset.mem_univ, if_true, Finset.sum_singleton, Finset.sum_erase_eq_sub] at h
  have hS := Finset.dvd_sum (s := .univ) fun j _ => h.1.2 j
  rw [Finset.sum_add_distrib, Finset.sum_sub_distrib, Fin.sum_const] at hS
  refine (((Int.isCoprime_iff_gcd_eq_one (n := 10)).mpr rfl).pow_right (n := i.1)).dvd_of_dvd_mul_right ?_
  exact (Int.dvd_sub (Int.dvd_sub hS (Int.dvd_add (h.1.2 i) (h.2.2 i))) (Int.dvd_mul_right 7 (∑ j, d j * 10 ^ j.1))).trans (dvd_of_eq (by ring1))

