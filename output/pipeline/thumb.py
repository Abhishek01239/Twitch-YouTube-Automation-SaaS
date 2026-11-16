import render as R, numpy as np, math
from PIL import Image, ImageFilter
from timeline import *
R.init()
O="/home/user/Twitch-YouTube-Automation-SaaS/output/"
# background: hero car shot with police lights
bg=R.SRC["C_11"]; sw,sh=bg.size; s=max(W/sw,H/sh)*1.12
bg=bg.resize((int(sw*s),int(sh*s)),Image.LANCZOS); x0=(bg.width-W)//2; y0=int(bg.height*0.5-H*0.42)
x=np.asarray(bg.crop((x0,y0,x0+W,y0+H)),np.float32)/255
x=R.grade(x); x=R.police(x,0.05,1.1); x=R.bloom(x,0.5); x=np.clip(x*R.VIG,0,1)
img=Image.fromarray((x*255).astype(np.uint8))
# protagonist cut-in (top) with soft feathered mask
face=R.SRC["F_42"]; fw=1080; face=face.resize((fw,int(face.height*fw/face.width)),Image.LANCZOS).crop((0,150,fw,1050))
m=Image.new("L",face.size,255); import PIL.ImageDraw as D
grad=np.ones((face.height,face.width),np.float32); grad*=(lambda v:v*v*(3-2*v))(np.clip((face.height-np.arange(face.height)[:,None])/520,0,1))
m=Image.fromarray((grad*255).astype(np.uint8))
fa=np.asarray(face,np.float32)/255; fa=np.clip(R.grade(fa),0,1); face=Image.fromarray((fa*255).astype(np.uint8))
img.paste(face,(0,0),m)
R.text(img,"VICE CITY","Anton.ttf",230,1020,glow=(255,20,150),glow_r=26)
R.text(img,"LOOKS INSANE","Anton.ttf",150,1225,fill=(255,215,60),glow=(255,70,0),glow_r=22)
R.hud_wanted(img,CHASE+10)
R.text(img,"FAN-MADE CONCEPT","Oswald.ttf",34,H-110,glow=None,spacing=3)
img.save(O+"thumbnail_1080x1920.jpg",quality=95)
# 16:9 version
t=Image.new("RGB",(1280,720))
bgw=R.SRC["G_99"]; sw,sh=bgw.size; s=1280/sw; bb=bgw.resize((1280,int(sh*s)),Image.LANCZOS); yy=int(bb.height*0.45)
bb=bb.crop((0,yy-360,1280,yy+360)); a=np.asarray(bb,np.float32)/255; a=np.clip(R.grade(a),0,1); t.paste(Image.fromarray((a*255).astype(np.uint8)))
f2=face.resize((540,450)); sm=lambda v:v*v*(3-2*v); m2=Image.fromarray((sm(np.clip(np.arange(540)[None,:]/220,0,1))*sm(np.clip(np.arange(450)[:,None]/160,0,1))*255).astype(np.uint8)); t.paste(f2,(740,270),m2)
R.W,R.H=1280,720
R.text(t,"VICE CITY","Anton.ttf",150,250,cx=420,glow=(255,20,150),glow_r=20)
R.text(t,"LOOKS INSANE","Anton.ttf",100,400,cx=420,fill=(255,215,60),glow=(255,70,0),glow_r=18)
t.save(O+"thumbnail_1280x720.jpg",quality=95)
