import json, math, subprocess, sys
T0,T1=float(sys.argv[1]),float(sys.argv[2])
from PIL import Image, ImageDraw, ImageFont
W,H,FPS,DUR=1280,720,24,180
lines=json.load(open('aligned.json'))
FMAIN=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',56)
FPAR=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf',40)
DIM=(150,140,170,255); HI=(255,238,190,255); PDIM=(120,120,140,255); PHI=(210,200,230,255); BALL=(255,120,70,255)
meas=ImageDraw.Draw(Image.new('RGBA',(1,1)))
def layout(l):
    f=FPAR if l['paren'] else FMAIN
    toks=l['text'].split()
    # map tokens to words: tokens count equals words count here
    assert len(toks)==len(l['w']),(toks,l['text'])
    widths=[meas.textlength(t+' ',font=f) for t in toks]
    x=(W-sum(widths))/2; y=H*0.62 if l['paren'] else H*0.55
    pos=[]
    for t,wd in zip(toks,widths): pos.append((t,x,y,wd)); x+=wd
    return f,pos
LAY=[layout(l) for l in lines]
def frame(t):
    im=Image.new('RGBA',(W,H),(0,0,0,0)); d=ImageDraw.Draw(im)
    act=None
    for i,l in enumerate(lines):
        nxt=lines[i+1]['s'] if i+1<len(lines) else DUR
        if l['s']-0.8<=t<min(nxt-0.05,l['e']+1.2): act=i;break
    if act is None: return im
    l=lines[act]; f,pos=LAY[act]
    # fade in/out
    a=1.0
    if t<l['s']: a=max(0,1-(l['s']-t)/0.8)
    for w,(txt,x,y,wd) in zip(l['w'],pos):
        on=t>=w['s']
        col=(PHI if on else PDIM) if l['paren'] else (HI if on else DIM)
        d.text((x,y),txt,font=f,fill=(col[0],col[1],col[2],int(255*a)))
    ball=None
    for i,w in enumerate(l['w']):
        s=w['s']; e=l['w'][i+1]['s'] if i+1<len(l['w']) else w['e']
        if s<=t<e or (i==0 and t<s):
            cx0=pos[i][1]+pos[i][3]/2-7; cx1=pos[i+1][1]+pos[i+1][3]/2-7 if i+1<len(l['w']) else cx0
            p=0 if t<s else (t-s)/max(e-s,0.01)
            cx=cx0+(cx1-cx0)*p; cy=pos[i][2]-28-abs(math.sin(p*math.pi))*60
            ball=(cx,cy);break
    if ball:
        r=15 if not l['paren'] else 11
        d.ellipse((ball[0]-r,ball[1]-r,ball[0]+r,ball[1]+r),fill=(BALL[0],BALL[1],BALL[2],int(255*a)))
    return im
p=subprocess.Popen(['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgba','-s',f'{W}x{H}','-r',str(FPS),'-i','-',
  '-c:v','prores_ks','-profile:v','4444','-pix_fmt','yuva444p10le',f'/home/claude/seg_{int(T0):03d}.mov'],stdin=subprocess.PIPE)
for fr in range(int(T0*FPS),int(T1*FPS)): p.stdin.write(frame(fr/FPS).tobytes())
p.stdin.close(); p.wait(); print('done')
