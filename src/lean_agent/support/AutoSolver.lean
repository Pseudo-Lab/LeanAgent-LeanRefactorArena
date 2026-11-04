import Lean

/-!
Diagnostic instrumentation, inlined after the pinned project's imports.
Adapted from PRs #41/#42 at 9fe17e58e78a1cbf67b171e01dc01b274e9d68ea:
experiments/verification-repair-policy/Support.lean (Week 4 LeanRepairSupport).
All positions are native UTF-8 byte offsets. See docs/common-harness/autosolver.md.
This helper is used only on a diagnostic copy, never to accept a final proof.
-/
namespace RecursiveRepairSupport
open Lean Elab Command

private meta def range (stx : Syntax) : List (String × Json) :=
  match stx.getPos?, stx.getTailPos? with
  | some a, some b => [("start", toJson a.byteIdx), ("end", toJson b.byteIdx)]
  | _, _ => []

private meta partial def blocks (stx : Syntax) : Array Json := Id.run do
  let mut found := #[]
  if stx.getKind == ``Lean.Parser.Term.byTactic then
    found := found.push <| Json.mkObj (range stx)
  for child in stx.getArgs do
    found := found ++ blocks child
  return found

private meta def goalJSON (goal : MVarId) : MetaM Json := goal.withContext do
  let target ← instantiateMVars (← goal.getType)
  let mut locals := #[]
  for decl in (← getLCtx) do
    let type ← instantiateMVars decl.type
    let value ← match decl.value? with
      | none => pure Json.null
      | some value => pure <| Json.str (← Meta.ppExpr (← instantiateMVars value)).pretty
    locals := locals.push <| Json.mkObj [
      ("name", toJson decl.userName.toString),
      ("binder_info", toJson (repr decl.binderInfo).pretty),
      ("type", toJson (← Meta.ppExpr type).pretty), ("value", value),
      ("implementation_detail", toJson decl.isImplementationDetail)]
  return Json.mkObj [
    ("target", toJson (← Meta.ppExpr target).pretty),
    ("local_context", Json.arr locals),
    ("display", toJson (← Meta.ppGoal goal).pretty)]

private meta partial def states (tree : InfoTree) (outer? : Option ContextInfo := none)
    (depth : Nat := 0) : IO (Array Json) := do
  match tree with
  | .context context tree => states tree (context.mergeIntoOuter? outer?) depth
  | .node info children =>
    let mut found := #[]
    if let .ofTacticInfo tactic := info then
      if let some context := outer? then
        let beforeCtx := { context with mctx := tactic.mctxBefore }
        let afterCtx := { context with mctx := tactic.mctxAfter }
        let before ← tactic.goalsBefore.toArray.mapM fun goal =>
          beforeCtx.runMetaM {} <| goalJSON goal
        let after ← tactic.goalsAfter.toArray.mapM fun goal =>
          afterCtx.runMetaM {} <| goalJSON goal
        found := found.push <| Json.mkObj <| range tactic.stx ++ [
          ("syntax_kind", toJson tactic.stx.getKind.toString),
          ("depth", toJson depth), ("before", toJson before), ("after", toJson after)]
    for child in children do
      found := found ++ (← states child outer? (depth + 1))
    return found
  | .hole _ => return #[]

elab "#recursive_repair_context " tag:str cmd:command : command => do
  let saved ← getResetInfoTrees
  try
    try
      withEnableInfoTree true <| elabCommand cmd
    finally
      let info ← getInfoState
      let mut tactics := #[]
      for tree in info.trees do
        tactics := tactics ++ (← liftIO <| states (tree.substitute info.assignment))
      let mut errors := #[]
      for message in (← get).messages.toList do
        if message.severity == .error then
          errors := errors.push <| Json.mkObj [
            ("position", toJson ((← getFileMap).ofPosition message.pos).byteIdx),
            ("code", toJson (message.errorName?.map Name.toString)),
            ("message", toJson (← message.data.toString))]
      let report := Json.mkObj [
        ("blocks", toJson (blocks cmd)), ("tactics", toJson tactics), ("errors", toJson errors)]
      logInfo m!"RECURSIVE_REPAIR {tag.getString} {report.compress}"
  finally
    let current ← getInfoState
    modifyInfoState fun state => { state with trees := saved.append current.trees }
end RecursiveRepairSupport
