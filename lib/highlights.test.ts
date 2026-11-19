import {test} from "node:test";
import assert from "node:assert/strict";
import {excitementCurve,pickCandidates,hypeScore,aiRank} from "./highlights";

const flat=(n:number,v:number)=>new Array(n).fill(v);
const overlaps=(start:number,end:number,from:number,to:number)=>start<to&&from<end;

test("finds a spike in a game that is loud the whole time",()=>{
  // -15 dB constant game audio with small noise, one burst to -3 dB at 300-306s.
  const loudness=Array.from({length:600},(_,i)=>-15+Math.sin(i*1.7)*1.5+(i>=300&&i<306?12:0));
  const [best]=pickCandidates(excitementCurve({loudness}),{length:30,count:1});
  assert.ok(overlaps(best.start,best.end,300,306),`picked ${best.start}-${best.end}`);
});

test("hype speech decides between two equally loud moments",()=>{
  const loudness=flat(600,-20);
  for(let i=100;i<105;i++)loudness[i]=-10; // loud, but the streamer is calm
  for(let i=420;i<425;i++)loudness[i]=-10; // just as loud, and the streamer is losing it
  const segments=[
    {start:100,end:105,text:"okay so I'm just driving to the mission"},
    {start:420,end:423,text:"OH MY GOD no way!"},
    {start:423,end:426,text:"LET'S GOOO clip that!!"}
  ];
  const [best]=pickCandidates(excitementCurve({loudness,segments}),{length:30,count:1,segments});
  assert.ok(overlaps(best.start,best.end,420,426),`picked ${best.start}-${best.end}`);
});

test("on-screen action counts as excitement",()=>{
  const loudness=flat(400,-18),motion=flat(400,0.02);
  for(let i=250;i<260;i++)motion[i]=0.6;
  const [best]=pickCandidates(excitementCurve({loudness,motion}),{length:30,count:1});
  assert.ok(overlaps(best.start,best.end,250,260));
});

test("action on a still screen is found even when audio has steady jitter",()=>{
  // Real-world case from an ffmpeg test video: ±0.2 dB audio wobble, one loud burst, one motion-only scene.
  const loudness=Array.from({length:180},(_,i)=>-38.3+Math.sin(i*2.3)*0.2+(i>=60&&i<64?21:0));
  const motion=Array.from({length:180},(_,i)=>i>=130&&i<140?13.6:0);
  const clips=pickCandidates(excitementCurve({loudness,motion}),{length:20,count:2});
  assert.ok(clips.some(c=>overlaps(c.start,c.end,60,64)),"loud burst");
  assert.ok(clips.some(c=>overlaps(c.start,c.end,130,140)),"motion scene");
});

test("clip includes build-up before the peak and does not overlap other clips",()=>{
  const loudness=flat(900,-20);
  for(const p of [200,500,800])for(let i=p;i<p+4;i++)loudness[i]=-5;
  const clips=pickCandidates(excitementCurve({loudness}),{length:30,count:3});
  assert.equal(clips.length,3);
  for(const c of clips){
    const into=(c.peak-c.start)/(c.end-c.start);
    assert.ok(into>0.3&&into<0.85,`peak at ${into.toFixed(2)} of clip`);
  }
  const sorted=[...clips].sort((a,b)=>a.start-b.start);
  for(let i=1;i<sorted.length;i++)assert.ok(sorted[i].start>=sorted[i-1].end);
});

test("cuts are moved to sentence boundaries",()=>{
  const loudness=flat(300,-20);for(let i=150;i<154;i++)loudness[i]=-4;
  const segments=Array.from({length:60},(_,i)=>({start:i*5,end:i*5+5,text:"words words words"}));
  const [c]=pickCandidates(excitementCurve({loudness,segments}),{length:30,count:1,segments});
  assert.equal(c.start%5,0);assert.equal(c.end%5,0);
});

test("hype phrases score above calm talk",()=>{
  assert.ok(hypeScore("OH MY GOD let's go, clip it!")>hypeScore("I am going to buy a car now"));
});

test("AI ranking falls back to signal order without a key",async()=>{
  const c=[{start:0,end:30,peak:10,score:1,transcript:""},{start:40,end:70,peak:50,score:5,transcript:""}];
  const ranked=await aiRank(c,1,{game:"GTA"});
  assert.equal(ranked[0].start,40);
});
