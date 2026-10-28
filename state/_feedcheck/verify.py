import json, sys, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import feedparser, requests
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept":"application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.5"}
feeds=json.load(open("config/feeds.json",encoding="utf-8"))
rows=[]
for f in feeds:
    try:
        r=requests.get(f["url"],headers=UA,timeout=20)
        code=r.status_code
        fd=feedparser.parse(r.content)
        n=len(fd.entries)
        latest=""
        if n:
            e=fd.entries[0]
            latest=(e.get("published") or e.get("updated") or "")[:10]
        err=""
        if n==0:
            err=str(getattr(fd,"bozo_exception",""))[:90].replace("\n"," ")
    except Exception as e:
        code=None; n=0; latest=""; err=type(e).__name__+": "+str(e)[:80]
    rows.append({"name":f["name"],"url":f["url"],"http":code,"items":n,"latest":latest,"err":err})
    print("%-24s http=%-5s items=%-4s %s"%(f["name"],code,n,err))
    time.sleep(0.25)
json.dump(rows,open("state/_feedcheck/final.json","w",encoding="utf-8"),indent=1)
ok=[r for r in rows if r["items"]>0]
print("LIVE OK", len(ok), "of", len(rows))
