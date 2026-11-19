// "Pro editor" for Shorts: builds the ffmpeg filter graph and animated caption file that turn a raw
// clip into a finished vertical Short (framing, word-by-word captions, hook title, punch-in zoom with
// impact sound, color grade, loudness normalization, progress bar, streamer credit).

export type Word={word:string;start:number;end:number};
export type Layout="blur"|"fill";
export type EditPlan={
  width:number;height:number;duration:number;
  words:Word[];
  hook?:string|null;       // big title shown for the first seconds
  credit?:string|null;     // e.g. twitch.tv/streamer, shown the whole time
  peak?:number|null;       // seconds into the clip where the punch-in + impact hit lands
  layout?:Layout;          // forced layout; otherwise picked from the aspect ratio
  hasAudio?:boolean;       // false when the clip has no audio track
};

const W=1080,H=1920;

export function chooseLayout(plan:Pick<EditPlan,"width"|"height"|"layout">):Layout{
  if(plan.layout)return plan.layout;
  return plan.width/plan.height>1.2?"blur":"fill"; // wide gameplay → blurred background; vertical clips fill
}

// Groups words into short caption "pages" (max 3 words / 14 chars), breaking on pauses and punctuation,
// like hand-made Shorts captions.
export function chunkWords(words:Word[],maxWords=3,maxChars=14){
  const chunks:Word[][]=[];let current:Word[]=[];
  for(const raw of words){
    const w={...raw,word:raw.word.trim()};
    if(!w.word)continue;
    const prev=current[current.length-1];
    const chars=current.reduce((n,x)=>n+x.word.length+1,0)+w.word.length;
    if(current.length&&(current.length>=maxWords||chars>maxChars||w.start-prev.end>0.6||/[.!?,]$/.test(prev.word))){chunks.push(current);current=[];}
    current.push(w);
  }
  if(current.length)chunks.push(current);
  return chunks;
}

function assTime(seconds:number){
  const cs=Math.max(0,Math.round(seconds*100));
  const h=Math.floor(cs/360000),m=Math.floor(cs%360000/6000),s=Math.floor(cs%6000/100),c=cs%100;
  return `${h}:${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}.${String(c).padStart(2,"0")}`;
}
const assText=(s:string)=>s.replace(/\{[^}]*\}/g,"").replace(/[\\{}]/g,"").replace(/\n/g," ").replace(/\s+/g," ").trim();
// Drop emoji and other glyphs the caption font cannot render (they show up as empty boxes).
const renderable=(s:string)=>s.replace(/[^\p{L}\p{N}\p{P}\p{Zs}$+=<>^`|~]/gu,"").replace(/\s+/g," ").trim();

const YELLOW="&H0000E5FF&",WHITE="&H00FFFFFF&";

export function buildAss(plan:EditPlan){
  const lines:string[]=[];
  // Captions: the whole chunk stays on screen, the word being spoken turns yellow and pops.
  for(const chunk of chunkWords(plan.words)){
    const chunkEnd=Math.min(plan.duration,chunk[chunk.length-1].end+0.15);
    chunk.forEach((word,i)=>{
      const start=word.start,end=i<chunk.length-1?chunk[i+1].start:chunkEnd;
      if(end<=start)return;
      const text=chunk.map((w,j)=>{
        const t=assText(renderable(w.word)).toUpperCase();
        return j===i?`{\\c${YELLOW}\\fscx112\\fscy112}${t}{\\c${WHITE}\\fscx100\\fscy100}`:t;
      }).join(" ");
      const popIn=i===0?"{\\fscx70\\fscy70\\t(0,90,\\fscx100\\fscy100)}":"";
      lines.push(`Dialogue: 1,${assTime(start)},${assTime(end)},Caption,,0,0,0,,${popIn}${text}`);
    });
  }
  const hook=plan.hook&&assText(renderable(plan.hook));
  if(hook)lines.push(`Dialogue: 2,${assTime(0)},${assTime(Math.min(3,plan.duration))},Hook,,0,0,0,,{\\fad(120,250)\\fscx85\\fscy85\\t(0,120,\\fscx100\\fscy100)}${hook}`);
  const credit=plan.credit&&assText(renderable(plan.credit));
  if(credit)lines.push(`Dialogue: 0,${assTime(0)},${assTime(plan.duration)},Credit,,0,0,0,,${credit}`);

  return `[Script Info]
ScriptType: v4.00+
PlayResX: ${W}
PlayResY: ${H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,DejaVu Sans,86,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,1,0,1,7,3,2,60,60,450,1
Style: Hook,DejaVu Sans,64,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,3,18,0,8,80,80,300,1
Style: Credit,DejaVu Sans,38,&H00FFFFFF,&H00FFFFFF,&H00000000,&H8C000000,1,0,0,0,100,100,0,0,3,10,0,8,60,60,150,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
${lines.join("\n")}
`;
}

const escapeFilterPath=(p:string)=>p.replace(/\\/g,"/").replace(/:/g,"\\:").replace(/'/g,"\\'");

// Zoom factor over time: a quick punch-in centered on the peak that eases back out.
function zoomExpr(peak:number|null|undefined,amount=0.14){
  if(peak==null)return "1";
  const p=peak.toFixed(2);
  return `(1+${amount}*exp(-pow((t-${p})/0.45,2)))`;
}

export function buildFilterGraph(plan:EditPlan,assPath:string){
  const layout=chooseLayout(plan);
  const z=zoomExpr(plan.peak);
  const grade="eq=contrast=1.07:saturation=1.2:brightness=0.01,unsharp=5:5:0.7";
  const v:string[]=[];
  if(layout==="blur"){
    // Background: the same clip, filled + blurred + darkened. Foreground: gameplay zoomed so the
    // action fills ~45% of the screen height, with the punch-in applied.
    const fgH=860;
    v.push(`[0:v]split=2[bgsrc][fgsrc]`);
    v.push(`[bgsrc]scale=${W}:${H}:force_original_aspect_ratio=increase,crop=${W}:${H},boxblur=24:3,eq=brightness=-0.12:saturation=1.1[bg]`);
    v.push(`[fgsrc]scale=w='trunc(${fgH}*${z}*iw/ih/2)*2':h='trunc(${fgH}*${z}/2)*2':eval=frame,crop='min(iw,${W})':${fgH},${grade}[fg]`);
    v.push(`[bg][fg]overlay=(W-w)/2:(H-h)/2-80,setsar=1[framed]`);
  }else{
    v.push(`[0:v]scale=${W}:${H}:force_original_aspect_ratio=increase,crop=${W}:${H},scale=w='trunc(${W}*${z}/2)*2':h=-2:eval=frame,crop=${W}:${H},${grade},setsar=1[framed]`);
  }
  // Progress bar sliding in along the bottom edge.
  const dur=Math.max(0.1,plan.duration).toFixed(2);
  v.push(`color=c=0xFFE500:s=${W}x14:r=30[bar]`);
  v.push(`[framed][bar]overlay=x='-w+w*t/${dur}':y=H-14:shortest=1:eval=frame[barred]`);
  v.push(`[barred]subtitles='${escapeFilterPath(assPath)}',format=yuv420p[vout]`);

  // Audio: impact hit on the peak (a synthesized sub-bass drop, so no licensing issues), then loudness
  // normalized to the -14 LUFS that Shorts/TikTok/Reels target.
  const a:string[]=[];
  const source=plan.hasAudio===false?`anullsrc=r=48000:cl=stereo,atrim=duration=${dur}`:`[0:a]aformat=sample_rates=48000:channel_layouts=stereo`;
  if(plan.peak!=null){
    const delay=Math.max(0,Math.round((plan.peak-0.05)*1000));
    a.push(`aevalsrc='0.9*sin(2*PI*(38+70*exp(-9*t))*t)*exp(-5*t)':s=48000:d=0.7,aformat=channel_layouts=stereo,adelay=${delay}|${delay}[hit]`);
    a.push(`${source}[main]`);
    a.push(`[main][hit]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]`);
  }else{
    a.push(`${source},loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]`);
  }
  return {filter:[...v,...a].join(";"),layout};
}

// Picks the punch-in moment: the most exciting second, ignoring the very start and end of the clip.
export function peakFromCurve(curve:number[]){
  if(curve.length<4)return null;
  let best=-1,bestValue=-Infinity;
  for(let i=1;i<curve.length-1;i++)if(curve[i]>bestValue){bestValue=curve[i];best=i;}
  return best>=0&&bestValue>0.5?best+0.5:null;
}
