import sys, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import requests, feedparser, time
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}
r=requests.get("https://kyivindependent.com/",headers=UA,timeout=25)
print("home",r.status_code,len(r.content))
links=sorted(set(re.findall(r'href="([^"]*(?:rss|feed)[^"]*)"',r.text)))
print("links:",links[:15])
for u in links[:8]:
    if u.startswith("/"): u="https://kyivindependent.com"+u
    try:
        rr=requests.get(u,headers=UA,timeout=20)
        print(u, rr.status_code, len(feedparser.parse(rr.content).entries))
    except Exception as e:
        print(u,"ERR",type(e).__name__)
