type MetadataInput={channelName?:string;game?:string;transcript?:string;keywords?:string[]};
const clean=(s:string)=>s.replace(/[#@]/g,"").replace(/\s+/g," ").trim();
export function generateMetadata(input:MetadataInput){
 const channel=clean(input.channelName||"Gaming"),game=clean(input.game||"Gaming");
 const words=(input.keywords||[]).map(clean).filter(Boolean).slice(0,8);
 const transcript=clean(input.transcript||"");
 const hint=transcript.split(" ").filter(Boolean).slice(0,12).join(" ");
 const title=((hint||words.slice(0,4).join(" ")||game+" highlight")+" 🔥").slice(0,100);
 const description=("Watch this "+game+" highlight from "+channel+". "+(hint?"Moment: "+hint+". ":"")+"Short-form gaming content for YouTube.").slice(0,5000);
 const tags=Array.from(new Set([game,channel,"gaming","gaming highlights","streamer","Twitch","YouTube Shorts",...words])).filter(Boolean).join(",").slice(0,500).split(",");
 const hashtags=Array.from(new Set(["#Shorts","#Gaming","#"+game.replace(/\W/g,""),...words.map(w=>"#"+w.replace(/\W/g,""))])).slice(0,8);
 return {title,description,tags,hashtags};
}