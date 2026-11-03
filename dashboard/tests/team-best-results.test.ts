import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {parseFinalBaselines} from '../src/lib/final-baselines.ts';
import {parseFinalResults} from '../src/lib/final-results.ts';
import {parseSummaryResults,mergeFinalResults} from '../src/lib/final-summary-results.ts';
import {parseSharedResults,selectTeamBest} from '../src/lib/team-best-results.ts';
import {resultSnapshot} from '../src/lib/final-snapshot.ts';
import {aggregate,parseSnapshot} from '../src/lib/model.ts';
const load=(name:string)=>JSON.parse(readFileSync(new URL(`../public/data/${name}.json`,import.meta.url),'utf8'));
const bases=parseFinalBaselines(load('final-baselines'));
const primary=parseFinalResults(load('final-results'),bases);
const somi=parseSummaryResults(load('physlib-cslib-results'),bases);
const incumbents=mergeFinalResults(primary,somi);
const shared=parseSharedResults(load('team-shared-results'),bases);

test('all 60 rows choose the highest reported score and retain all 80 source candidates',()=>{
 const best=selectTeamBest(incumbents,shared);
 assert.equal(best.problems.length,60);
 assert.deepEqual(best.problems.map(p=>p.row),Array.from({length:60},(_,i)=>i+1));
 assert.equal(best.problems.reduce((s,p)=>s+p.comparisons!.length,0),80);
 for(const p of best.problems){
  assert.equal(p.comparisons!.filter(c=>c.selected).length,1);
  assert.ok(p.comparisons!.every(c=>c.score<=p.score+1e-9));
  assert.equal(p.comparisons!.find(c=>c.selected)!.candidateHash,p.candidateHash);
 }
 const snapshot=parseSnapshot(resultSnapshot(bases,best));
 assert.equal(aggregate(snapshot.problems,'combined').count,60);
 assert.ok(Math.abs(aggregate(snapshot.problems,'combined').value!-best.problems.reduce((s,p)=>s+p.score,0)/60)<1e-9);
 assert.equal('auditPassed' in best,false);
});

test('Strata and LeanPool preserve the original 20 proofs, paired measurements and scores',()=>{
 const best=selectTeamBest(incumbents,shared);
 for(const old of primary.problems){
  const current=best.problems.find(p=>p.row===old.row)!;
  for(const key of ['candidateHash','proof','score','baseline','candidate','versions'] as const) assert.deepEqual(current[key],old[key]);
  assert.equal(current.author,'권주원');
 }
 const reference=best.problems.find(p=>p.row===11)!;
 assert.equal(reference.author,'정소미'); // incumbent wins a mathematical tie
});

test('shared observations cannot claim a fresh compiler run, alter score, scope, samples or versions',()=>{
 for(const change of [(x:any)=>x.leanRunsDuringImport=1,(x:any)=>x.apiCallsDuringImport=1,
  (x:any)=>x.problems[0].score=100,(x:any)=>x.problems[0].row=1,
  (x:any)=>x.problems[0].author='wrong',(x:any)=>x.problems[0].versions[0].status='fail',
  (x:any)=>x.problems[0].versions[0].revision='0'.repeat(40),
  (x:any)=>x.problems[30].candidate.raw_samples=[1,2,3],
  (x:any)=>x.problems[0].proofPath='../wrong.lean',
 ]) {const data=load('team-shared-results');change(data);assert.throws(()=>parseSharedResults(data,bases));}
});
