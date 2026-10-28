import json, sys, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ch=json.load(open("config/channels.json",encoding="utf-8"))
pf=json.load(open(r"C:\Users\MarciNaro\.config\opencode\home\youtube-manager\channel_portfolio.json",encoding="utf-8-sig"))
pids={x["channelId"] for x in pf}
pnames={x["title"].strip().lower(): x["channelId"] for x in pf}
req=["Asmongold","Asmongold TV","Asmongold Clips","Asmongold Shorts","Asmongold Gaming","penguinz0","MoistCr1TiKaL","AngryJoeShow","videogamedunkey","MeatCanyon","Papa Meat","Viva La Dirt League","Flashgitz","Fern","Visual Venture","POI","Cryton","Ahoy","Internet Historian","NakeyJakey","Drew Gooden","Super Eyepatch Wolf","h3h3","Gigguk","Dr Insanity","Naked Criminal","Vsauce","ANATOLY","MrBeast","JT Music","Teminite","skeler.","AI Explained","Matt Wolfe","AI Search","Two Minute Papers","bycloud","Dr. Plants","Odd Animal Specimens","Scary Interesting","blameitonjorge","Nexpo","Curious Archive","Real Science"]
have={x["name"].strip().lower():x for x in ch}
missing=[]
for r in req:
    k=r.lower()
    if k in have: continue
    alt={"h3h3":"h3h3productions","poi":"poi","fern":"fern","skeler.":"skeler.","dr. plants":"dr. plants"}.get(k)
    if alt and alt in have: continue
    missing.append(r)
print("MISSING:", missing if missing else "none")
print("total", len(ch), "not-in-portfolio:", [(x["name"],x["id"]) for x in ch if x["id"] not in pids])
bad=[x["id"] for x in ch if not re.fullmatch(r"UC[A-Za-z0-9_-]{22}", x["id"])]
print("bad ids:", bad)
print("dup ids:", len(ch)-len({x["id"] for x in ch}))
print("extra keys:", sorted({k for x in ch for k in x} - {"id","name","tier","tags","enabled","note"}))
print("qualified required names:", len(req)-len(missing), "of", len(req))
