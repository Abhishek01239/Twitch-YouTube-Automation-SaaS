import urllib.parse, urllib.request, sys, os, time, concurrent.futures as cf
OUT=sys.argv[1]
STY=", AAA open world video game graphics, unreal engine 5, ray traced reflections, hyper detailed, photorealistic, cinematic color grading, no text, no logo"
P={
"A":("breathtaking aerial drone shot of a tropical miami style coastal metropolis at golden hour sunset, glass skyscrapers glowing orange and pink, art deco hotels on the beach, palm trees, turquoise ocean, busy boulevards, dramatic purple orange sky, god rays",576,1024),
"B":("wide side view of a neon lit miami style beachfront boulevard at dusk, art deco buildings with pink and cyan neon, palm trees, people on sidewalk, wet asphalt road reflecting neon, deep blue twilight sky",1024,576),
"C":("low angle front shot of a glossy magenta exotic supercar speeding toward camera on a wet neon lit miami city street at night, bright headlights, motion blur, palm trees, pink and cyan neon reflections, light rain",576,1024),
"D":("side view tracking shot of a glossy magenta exotic supercar racing along a neon miami beach boulevard at night, strong horizontal motion blur background, palm trees, neon lights streaks, wet road",576,1024),
"E":("cinematic shot of a confident stylish criminal man with short beard wearing open floral shirt, gold chain and sunglasses walking toward camera through a crowded neon nightclub, magenta and cyan lasers, haze, backlight",576,1024),
"F":("dramatic close up portrait of a stylish criminal man with short beard, open floral shirt, gold chain, sunglasses, smirking, dark neon nightclub, magenta and cyan rim light, bokeh",576,1024),
"G":("night police chase on a miami coastal highway, magenta supercar in front fleeing toward camera, police cars behind with flashing red and blue lights, motion blur, glowing skyline, wet road reflections",576,1024),
"H":("magenta supercar drifting sideways at a city intersection at night with thick white tire smoke, police car with red and blue lights behind, neon art deco buildings, palm trees, wet asphalt, low angle",576,1024),
"I":("extreme low angle close up of the front of a police car racing through a rainy neon city street at night, red and blue siren lights blazing, headlights flare, water spray, motion blur",576,1024),
"J":("beautiful night aerial view of a miami style city, skyscrapers lit in pink purple and cyan neon, reflections on the bay, illuminated causeway bridge with car light trails, palm lined beach, full moon",576,1024),
"L":("rear view of three police cars with flashing red and blue light bars chasing at high speed down a neon miami city street at night, motion blur, sparks, wet road reflections",576,1024),
"M":("magenta supercar drifting with huge white tire smoke clouds, side view, neon city street at night, red and blue police lights glowing through the smoke",576,1024),
"K":("cinematic view from behind of a man in an open floral shirt standing on a skyscraper rooftop at night overlooking a vast glowing neon miami style city skyline, pink purple cyan lights, moonlit clouds",576,1024),
}
def get(k,seed):
    p,w,h=P[k]; fn=f"{OUT}/{k}_{seed}.jpg"
    if os.path.exists(fn): return fn
    url="https://image.pollinations.ai/prompt/"+urllib.parse.quote(p+STY)+f"?width={w}&height={h}&seed={seed}&nologo=true"
    for a in range(4):
        try:
            d=urllib.request.urlopen(url,timeout=180).read()
            if d[:2]==b'\xff\xd8': open(fn,'wb').write(d); return fn
        except Exception as e: print(k,seed,e)
        time.sleep(5)
    return None
keys=sys.argv[2] if len(sys.argv)>2 else "".join(P)
seeds=[int(s) for s in (sys.argv[3] if len(sys.argv)>3 else "11,42").split(",")]
with cf.ThreadPoolExecutor(1) as ex:
    for r in ex.map(lambda a:get(*a),[(k,s) for k in keys for s in seeds]): print(r)
