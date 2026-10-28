import json, sys, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import requests, feedparser
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept":"application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.5"}
fe=json.load(open("config/feeds.json",encoding="utf-8"))
rows=[]
for f in fe:
    try:
        r=requests.get(f["url"],headers=UA,timeout=20)
        n=len(feedparser.parse(r.content).entries); code=r.status_code
    except Exception as e:
        code="ERR"; n=0
    rows.append((f["name"],f["url"],code,n,f["tags"],f["weight"]))
    print("%-24s %-5s %-5s"%(f["name"],code,n))
    time.sleep(0.2)
dead=[r for r in rows if not (r[2]==200 and r[3]>0)]
print("LIVE",len(rows)-len(dead),"of",len(rows))
print("DEAD:",[d[0] for d in dead])
json.dump([{"name":r[0],"url":r[1],"http":r[2],"items":r[3],"tags":r[4],"weight":r[5]} for r in rows],
          open("state/_feeds_now.json","w",encoding="utf-8"),indent=1)
