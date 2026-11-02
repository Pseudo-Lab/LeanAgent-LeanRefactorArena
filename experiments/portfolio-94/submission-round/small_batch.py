from pathlib import Path
import json
from probe_small import evaluate,E,W

selection=json.loads((E/'submission-round/selection-baseline.json').read_text())['proofs']

def code(n):return Path(selection[str(n)]).read_text()

if __name__=='__main__':
 for n in [4,13,14,15,1,2]:
  pin='4.26.0' if n in [1,2,14] else None
  seed=code(n)
  result=evaluate(n,seed,'baseline',pin)
  if not result['valid']:continue
  variants={}
  if n==4:
   variants['explicit_inner']=seed.replace('by fun_prop','hf.inner continuous_const')
   variants['inferred_inner']=seed.replace('have hc : Continuous fun y => ⟪f y, f x⟫_ℝ := by fun_prop','have hc := hf.inner (continuous_const (y := f x))')
  if n==15:
   variants['closed_decide']=seed.replace('by norm_num','by decide')
   variants['closed_kernel']=seed.replace('by norm_num','by decide +kernel')
   variants['no_push_cast']=seed.replace('push_cast; ring','ring1')
   variants['closed_decide_no_push']=variants['closed_decide'].replace('push_cast; ring','ring1')
  if n==13:
   variants['instantiate_bounds']=seed.replace('0 < k ∧ k ≤ m','0 < k ∧ k ≤ m').replace('ih (m - k) (by omega)','ih (m - k) (Nat.sub_lt (by omega) hk.1)')
  if n==1:
   variants['lemma_direct_leaves']=seed.replace('grind only []','simp_all only [or_self, or_true, true_or]')
  if n==2:
   variants['explicit_sublist_constructor']=seed.replace('all_goals apply_rules only [List.Sublist.append, List.nil_sublist, List.Sublist.refl, *]','all_goals first | exact List.nil_sublist _ | exact List.Sublist.refl _ | exact List.Sublist.append ‹_› ‹_›')
  for label,candidate in variants.items():
   if candidate!=seed:evaluate(n,candidate,label,pin)
