// Highlight detection: decides which moments of a long recording make the best Shorts.
// Combines several signals per second of video, then picks and AI-ranks the best windows.

export type Segment={start:number;end:number;text:string};
export type Candidate={start:number;end:number;peak:number;score:number;transcript:string};

// Phrases streamers say at hype moments. Weighted roughly by how strongly they signal a highlight.
const HYPE:Array<[RegExp,number]>=[
  [/\b(oh my god|omg|oh my gosh)\b/gi,3],[/\b(let'?s go+|lets go+|lfg)\b/gi,3],[/\b(no way|no shot|are you serious|are you kidding)\b/gi,3],
  [/\b(what the (hell|heck|fuck)|wtf)\b/gi,3],[/\b(holy (shit|crap|moly)|bro what|yo+)\b/gi,2.5],[/\b(clip (it|that)|clipped)\b/gi,4],
  [/\b(insane|crazy|unbelievable|nuts|wild|clutch|massive|huge)\b/gi,2],[/\b(run|go go|drive|get in|shoot|cops?|police|chase|explod\w*|crash\w*)\b/gi,1],
  [/\b(ha(ha)+|lmao|lol)\b/gi,2],[/\b(no+ ?no+|nooo+|wait wait|help)\b/gi,2],[/!/g,0.5]
];

export function hypeScore(text:string){
  let score=0;
  for(const [pattern,weight] of HYPE)score+=(text.match(pattern)?.length||0)*weight;
  return score;
}

function median(values:number[]){
  if(!values.length)return 0;
  const sorted=[...values].sort((a,b)=>a-b),mid=sorted.length>>1;
  return sorted.length%2?sorted[mid]:(sorted[mid-1]+sorted[mid])/2;
}

// Converts a raw signal into "how unusual is this second compared with the surrounding minute".
// That way a constantly loud game doesn't drown out a genuine spike, and a quiet stream still has peaks.
export function relativeSpikes(values:number[],radius=30){
  const raw=values.map((v,i)=>v-median(values.slice(Math.max(0,i-radius),i+radius+1)));
  const positive=raw.map(v=>Math.max(0,v));
  // Scale by typical deviation, but never below 5% of the signal's overall range: tiny wobble in a
  // steady signal must not look like excitement, and a signal that is flat until the action starts
  // (e.g. motion) must still register strongly.
  const sorted=[...values].sort((a,b)=>a-b);
  const range=sorted.length?sorted[sorted.length-1]-sorted[Math.floor((sorted.length-1)*0.05)]:0;
  const typical=median(raw.map(Math.abs)); // typical second-to-second variation across the whole recording
  const spread=Math.max(typical,0.08*range)||1;
  return positive.map(v=>Math.min(v/spread,6));
}

function smooth(values:number[],radius=2){
  return values.map((_,i)=>{const w=values.slice(Math.max(0,i-radius),i+radius+1);return w.reduce((a,b)=>a+b,0)/w.length;});
}

// Combined excitement per second: audio spikes + sudden loudness jumps + on-screen action + hype speech.
export function excitementCurve(input:{loudness:number[];motion?:number[];segments?:Segment[]}){
  const n=input.loudness.length;
  const audio=relativeSpikes(input.loudness);
  const jumps=relativeSpikes(input.loudness.map((v,i)=>i?Math.max(0,v-input.loudness[i-1]):0),15);
  const motion=input.motion?.length?relativeSpikes(Array.from({length:n},(_,i)=>input.motion![i]||0)):new Array(n).fill(0);
  const speech=new Array(n).fill(0);
  for(const s of input.segments||[]){
    const hype=hypeScore(s.text);
    const words=s.text.trim().split(/\s+/).filter(Boolean).length;
    const rate=words/Math.max(0.5,s.end-s.start);
    const value=hype+(rate>3.5?1:0); // fast, excited talking
    for(let t=Math.floor(s.start);t<=Math.min(n-1,Math.floor(s.end));t++)speech[t]+=value;
  }
  const speechNorm=speech.map(v=>Math.min(v/3,6));
  return smooth(audio.map((a,i)=>1.0*a+0.6*jumps[i]+0.7*motion[i]+0.9*speechNorm[i]));
}

function transcriptBetween(segments:Segment[],start:number,end:number){
  return segments.filter(s=>s.end>start&&s.start<end).map(s=>s.text.trim()).join(" ").replace(/\s+/g," ").trim();
}

// Moves a cut so it doesn't land mid-sentence (only if a sentence boundary is close by).
function snap(time:number,segments:Segment[],edge:"start"|"end",maxShift=3){
  let best=time,bestDist=maxShift+0.001;
  for(const s of segments){
    const t=edge==="start"?s.start:s.end;
    const inside=s.start<time&&time<s.end;
    const d=Math.abs(t-time);
    if(inside&&d<bestDist){best=t;bestDist=d;}
  }
  return best;
}

// Picks the strongest non-overlapping windows. Each window is placed so the peak lands about 60%
// of the way through: viewers get the build-up and the payoff, and the clip ends shortly after.
export function pickCandidates(curve:number[],opts:{length:number;count:number;segments?:Segment[]}):Candidate[]{
  const n=curve.length,len=Math.min(opts.length,n),segments=opts.segments||[];
  if(!n)return [];
  const prefix=[0];for(const v of curve)prefix.push(prefix[prefix.length-1]+v);
  const windows:Candidate[]=[];
  for(let start=0;start+len<=n;start++){
    let peak=start;for(let t=start;t<start+len;t++)if(curve[t]>curve[peak])peak=t;
    const mean=(prefix[start+len]-prefix[start])/len;
    // Reward a strong peak placed after some build-up, not a peak in the first second.
    const placement=1-Math.abs((peak-start)/len-0.6);
    windows.push({start,end:start+len,peak,score:mean+0.5*curve[peak]*placement,transcript:""});
  }
  windows.sort((a,b)=>b.score-a.score);
  const picked:Candidate[]=[];
  for(const w of windows){
    if(picked.length>=opts.count)break;
    if(picked.some(p=>w.start<p.end&&p.start<w.end))continue;
    if(picked.some(p=>Math.abs(p.peak-w.peak)<len))continue;
    const start=Math.max(0,snap(w.start,segments,"start"));
    const end=Math.min(n,snap(w.end,segments,"end"));
    picked.push({...w,start,end,transcript:transcriptBetween(segments,start,end)});
  }
  return picked;
}

export type RankedClip=Candidate&{title?:string;reason?:string};

// Optional AI judge: given the top candidates' transcripts and signal scores, ranks which will
// perform best as Shorts and writes a title. Falls back to signal ranking if no LLM is configured.
export async function aiRank(candidates:Candidate[],count:number,opts:{game:string;apiKey?:string;model?:string}):Promise<RankedClip[]>{
  const fallback=[...candidates].sort((a,b)=>b.score-a.score).slice(0,count);
  if(!opts.apiKey||candidates.length<=1)return fallback;
  const list=candidates.map((c,i)=>`#${i} | ${Math.round(c.start)}s-${Math.round(c.end)}s | signal ${c.score.toFixed(1)} | transcript: ${c.transcript.slice(0,600)||"(no speech)"}`).join("\n");
  try{
    const response=await fetch("https://api.groq.com/openai/v1/chat/completions",{
      method:"POST",
      headers:{Authorization:`Bearer ${opts.apiKey}`,"Content-Type":"application/json"},
      body:JSON.stringify({
        model:opts.model||"llama-3.3-70b-versatile",temperature:0.2,response_format:{type:"json_object"},
        messages:[
          {role:"system",content:"You are an expert short-form video editor for gaming YouTube Shorts and TikTok. You pick moments with the strongest hook, payoff, humor or chaos. Signal = audio/motion/hype intensity measured from the video. Reply with JSON only."},
          {role:"user",content:`Game: ${opts.game}\nCandidate moments:\n${list}\n\nPick the best ${count}. Return {"clips":[{"index":number,"title":"catchy title under 70 chars, no hashtags","reason":"short"}]} ordered best first.`}
        ]
      })
    });
    if(!response.ok)throw new Error(`${response.status}`);
    const data=await response.json() as {choices:Array<{message:{content:string}}>};
    const parsed=JSON.parse(data.choices[0].message.content) as {clips?:Array<{index:number;title?:string;reason?:string}>};
    const seen=new Set<number>();
    const ranked:RankedClip[]=(parsed.clips||[]).filter(c=>Number.isInteger(c.index)&&candidates[c.index]&&!seen.has(c.index)&&seen.add(c.index))
      .map((c):RankedClip=>({...candidates[c.index],title:c.title?.replace(/#\S+/g,"").trim().slice(0,90),reason:c.reason}));
    for(const c of fallback)if(ranked.length<count&&!ranked.some(r=>r.start===c.start))ranked.push(c);
    return ranked.slice(0,count);
  }catch(error){
    console.error("AI ranking unavailable, using signal ranking:",error instanceof Error?error.message:String(error));
    return fallback;
  }
}
