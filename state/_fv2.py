import json, sys, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import requests, feedparser
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
fe=json.load(open("config/feeds.json",encoding="utf-8"))
bad=[]
for f in fe:
    try:
        r=requests.get(f["url"],headers=UA,timeout=20); n=len(feedparser.parse(r.content).entries); code=r.status_code
    except Exception: code="ERR"; n=0
    if not(code==200 and n>0): bad.append((f["name"],code,n))
    print("%-24s %-5s %-4s"%(f["name"],code,n)); time.sleep(0.2)
print("dead:",bad)
