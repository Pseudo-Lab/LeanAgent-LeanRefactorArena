import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {parseFinalBaselines} from '../src/lib/final-baselines.ts';
import {parseFinalResults} from '../src/lib/final-results.ts';
import {parseSummaryResults,mergeFinalResults} from '../src/lib/final-summary-results.ts';
import {resultSnapshot} from '../src/lib/final-snapshot.ts';
import {parseSnapshot,aggregate,valueOf} from '../src/lib/model.ts';
const load=(name:string)=>JSON.parse(readFileSync(new URL(`../public/data/${name}.json`,import.meta.url),'utf8'));
const bases=parseFinalBaselines(load('final-baselines'));
test('40 disjoint rows preserve scores and missing samples without a whole-set score',()=>{
 const first=parseFinalResults(load('final-results'),bases),second=parseSummaryResults(load('physlib-cslib-results'),bases);
 const combined=mergeFinalResults(first,second),snapshot=parseSnapshot(resultSnapshot(bases,combined));
 assert.equal(combined.problems.length,40);assert.equal(snapshot.problems.filter(p=>p.candidate).length,40);
 assert.equal('auditPassed' in combined,false);assert.equal('apiCalls' in combined,false);
 assert.equal(aggregate(snapshot.problems,'combined').value,null);
 assert.ok(Math.abs(combined.problems.reduce((s,p)=>s+p.score,0)/40-65.27889040403838)<1e-9);
 for(const row of second){
  assert.equal(row.baseline.raw_samples,null);assert.equal(row.candidate.raw_samples,null);
  assert.ok(row.versions.every(v=>v.fingerprint===null));
  assert.equal(createHash('sha256').update(row.proof).digest('hex'),row.candidateHash);
  const file=readFileSync(new URL(`../../${row.proofPath}`,import.meta.url),'utf8');
  assert.equal(createHash('sha256').update(file).digest('hex'),row.proofFileHash);assert.equal(file,row.proof+'\n');
  assert.ok(Math.abs(valueOf(snapshot.problems.find(p=>p.id===row.row)!,'combined')!-row.score)<1e-9);
 }
 assert.throws(()=>mergeFinalResults(first,[...second,...second]),/중복/);
});
test('reject invalid identity, scope, pins, hashes, validity, repeat counts, API claims and scores',()=>{
 for(const change of [(x:any)=>x.results[0].name='wrong',(x:any)=>x.results[0].row=1,
  (x:any)=>x.results[1]=x.results[0],(x:any)=>x.results[0].versions[0]={'v4.34.1':'0'.repeat(40)},
  (x:any)=>x.results[0].proof_sha256='fake',(x:any)=>x.results[0].checks['physlib-v4.34.1'].valid=false,
  (x:any)=>x.results[0].checks['physlib-v4.34.1'].repeats=0,(x:any)=>x.api_calls=1,
  (x:any)=>x.results[0].score_local=100,(x:any)=>x.local_mean=100,
 ]){const data=load('physlib-cslib-results');change(data);assert.throws(()=>parseSummaryResults(data,bases));}
});
