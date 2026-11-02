import Lean

/- Diagnostic metaprogram, not a submitted proof. It never calls a counter setter.
   The experiment measures the counter restoration performed inside Lean itself. -/
open Lean Meta Elab Command

structure WorkKey where
  n : Nat
deriving BEq, Hashable, TypeName

structure WorkResult where
  answer : Nat
  inner : Nat
deriving TypeName

def allocationWork (n : Nat) : MetaM WorkResult := do
  let before ← IO.getNumHeartbeats
  let mut answer := 0
  for _ in [0:n] do
    let e ← mkFreshExprMVar (some (mkConst ``Nat))
    answer := answer + if e.isMVar then 1 else 0
  let after ← IO.getNumHeartbeats
  return ⟨answer, after - before⟩

run_cmd liftCoreM <| MetaM.run' do
  let n := 1000
  let b0 ← IO.getNumHeartbeats
  let direct ← allocationWork n
  let a0 ← IO.getNumHeartbeats
  let enabled := (← getEnv).areRealizationsEnabledForConst ``Nat.add
  let b1 ← IO.getNumHeartbeats
  let cold ← realizeValue ``Nat.add ({ n } : WorkKey) (allocationWork n)
  let a1 ← IO.getNumHeartbeats
  let b2 ← IO.getNumHeartbeats
  let warm ← realizeValue ``Nat.add ({ n } : WorkKey) (allocationWork n)
  let a2 ← IO.getNumHeartbeats
  unless direct.answer == cold.answer && cold.answer == warm.answer do
    throwError "workload mismatch"
  logInfo m!"REALIZE enabled={enabled} answer={direct.answer} direct_outer={a0-b0} direct_inner={direct.inner} cold_outer={a1-b1} cold_inner={cold.inner} warm_outer={a2-b2} cached_inner={warm.inner}"
