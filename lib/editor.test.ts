import {test} from "node:test";
import assert from "node:assert/strict";
import {chunkWords,buildAss,buildFilterGraph,chooseLayout,peakFromCurve} from "./editor";

const words=(text:string,gap=0.4)=>text.split(" ").map((w,i)=>({word:w,start:i*gap,end:i*gap+gap*0.8}));
const base={width:1920,height:1080,duration:10,words:[] as ReturnType<typeof words>};

test("captions are short pages that break on punctuation and pauses",()=>{
  const chunks=chunkWords([...words("oh my god no way, let's go"),{word:"again",start:10,end:10.3}]);
  assert.deepEqual(chunks.map(c=>c.map(w=>w.word).join(" ")),["oh my god","no way,","let's go","again"]);
  assert.ok(chunks.every(c=>c.length<=3));
});

test("each spoken word gets its own highlighted caption line",()=>{
  const ass=buildAss({...base,words:words("cops behind me")});
  const lines=ass.split("\n").filter(l=>l.startsWith("Dialogue: 1"));
  assert.equal(lines.length,3);
  assert.match(lines[1],/COPS \{\\c&H0000E5FF&.*\}BEHIND\{/);
});

test("hook and credit are added and cleaned of emoji and override braces",()=>{
  const ass=buildAss({...base,hook:"Escaping 5 stars 🚔 {\\b0}",credit:"twitch.tv/someone"});
  assert.match(ass,/,Hook,.*Escaping 5 stars\s*$/m);
  assert.doesNotMatch(ass,/🚔|\\b0/);
  assert.match(ass,/,Credit,.*twitch\.tv\/someone/);
});

test("wide gameplay gets the blurred background layout, vertical clips fill the screen",()=>{
  assert.equal(chooseLayout({width:1920,height:1080}),"blur");
  assert.equal(chooseLayout({width:1080,height:1920}),"fill");
  assert.equal(chooseLayout({width:1920,height:1080,layout:"fill"}),"fill");
});

test("punch-in and impact hit are added only when there is a peak",()=>{
  const withPeak=buildFilterGraph({...base,peak:4.5},"/tmp/a.ass").filter;
  assert.match(withPeak,/t-4\.50/);assert.match(withPeak,/aevalsrc/);assert.match(withPeak,/adelay=4450\|4450/);
  const without=buildFilterGraph({...base,peak:null},"/tmp/a.ass").filter;
  assert.doesNotMatch(without,/aevalsrc|t-/);
  assert.match(buildFilterGraph({...base,hasAudio:false},"/tmp/a.ass").filter,/anullsrc/);
});

test("peak ignores the first and last second and needs real excitement",()=>{
  assert.equal(peakFromCurve([9,0,0,3,0,9]),3.5);
  assert.equal(peakFromCurve([0,0.1,0.2,0.1,0]),null);
});
