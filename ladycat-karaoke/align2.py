import re, json, torch, torchaudio, soundfile as sf, torchaudio.functional as F
d,sr=sf.read('a16.wav',dtype='float32')
bundle=torchaudio.pipelines.WAV2VEC2_ASR_BASE_960H
model=bundle.get_model().eval(); labels=bundle.get_labels(); lab={c:i for i,c in enumerate(labels)}
lines=[]; sec=None
for ln in open('lyrics.txt'):
    ln=ln.strip()
    if not ln: continue
    if ln.startswith('['): sec=ln.strip('[]'); continue
    lines.append({'section':sec,'text':ln,'paren':ln.startswith('('),'words':re.findall(r"[a-z']+", ln.lower())})
regions=[(16.5,67.5,['Verse 1','Pre-Chorus','Chorus']),(85.5,163,['Verse 2','Pre-Chorus','Final Chorus','Outro'])]
def align(t0,t1,words):
    wav=torch.from_numpy(d[int(t0*sr):int(t1*sr)])[None,:]
    ems=[]
    with torch.inference_mode():
        for i in range(0,wav.shape[1],20*sr):
            e,_=model(wav[:,i:i+20*sr]); ems.append(e[0])
    em=torch.log_softmax(torch.cat(ems,0),-1)[None]
    tr="|".join(w.upper() for w in words); tg=torch.tensor([[lab[c] for c in tr if c in lab]])
    ali,sc=F.forced_align(em,tg,blank=0); spans=F.merge_tokens(ali[0],sc[0].exp())
    ratio=wav.shape[1]/em.shape[1]; ws=[];cur=[]
    for s in spans:
        if labels[s.token]=='|':
            if cur: ws.append(cur);cur=[]
        else: cur.append(s)
    if cur: ws.append(cur)
    return [(round(t0+w[0].start*ratio/sr,2),round(t0+w[-1].end*ratio/sr,2)) for w in ws]

idx=[i for i,l in enumerate(lines) if l['section']=='Verse 2'][0]
groups=[(regions[0][0],regions[0][1],lines[:idx]),(regions[1][0],regions[1][1],lines[idx:])]
for t0,t1,sel in groups:
    words=[w for l in sel for w in l['words']]
    ts=align(t0,t1,words); i=0
    for l in sel:
        l['w']=[]
        for w in l['words']:
            l['w'].append({'w':w,'s':ts[i][0],'e':ts[i][1]}); i+=1
        l['s']=l['w'][0]['s']; l['e']=l['w'][-1]['e']
json.dump(lines,open('aligned.json','w'),indent=1)
for l in lines: print(f"{l['s']:7.2f}-{l['e']:7.2f} {'  ' if l['paren'] else ''}{l['text']}")
