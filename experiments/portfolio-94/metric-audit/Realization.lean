import Lean

/- Diagnostic metaprogram, not a submitted proof. It never calls a counter setter.
   The experiment measures the counter restoration performed inside Lean itself. -/
open Lean Meta Elab Command

def allocationWork (n : Nat) : MetaM (Nat × Nat) := do
  let before ← IO.getNumHeartbeats
  let expressions := (List.range n).map fun i => mkApp (mkConst ``Nat.succ) (mkNatLit i)
  let answer := expressions.foldl (fun acc e => acc + e.appArg!.natLit!) 0
  let after ← IO.getNumHeartbeats
  return (answer, after - before)

run_cmd liftCoreM <| MetaM.run' do
  let n := 10000
  let b0 ← IO.getNumHeartbeats
  let direct ← allocationWork n
  let a0 ← IO.getNumHeartbeats
  let enabled := (← getEnv).areRealizationsEnabledForConst ``Nat.add
  let b1 ← IO.getNumHeartbeats
  let cold ← realizeValue ``Nat.add (`metricAllocationProbe, n) (allocationWork n)
  let a1 ← IO.getNumHeartbeats
  let b2 ← IO.getNumHeartbeats
  let warm ← realizeValue ``Nat.add (`metricAllocationProbe, n) (allocationWork n)
  let a2 ← IO.getNumHeartbeats
  unless direct.1 == cold.1 && cold.1 == warm.1 do
    throwError "workload mismatch"
  logInfo m!"REALIZE enabled={enabled} answer={direct.1} direct_outer={a0-b0} direct_inner={direct.2} cold_outer={a1-b1} cold_inner={cold.2} warm_outer={a2-b2} cached_inner={warm.2}"
