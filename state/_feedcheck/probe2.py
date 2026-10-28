import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import feedparser, requests, time
UA={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept":"application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.5"}
TRIES=[
 ("DF1","https://www.eurogamer.net/digitalfoundry/rss"),
 ("DF2","https://feeds.feedburner.com/digitalfoundry"),
 ("DF3","https://www.eurogamer.net/feed/digitalfoundry"),
 ("DF4","https://www.digitalfoundry.net/feed"),
 ("KI1","https://kyivindependent.com/feed/"),
 ("KI2","https://kyivindependent.com/rss/"),
 ("KI3","https://kyivindependent.com/.rss/full/"),
 ("KI4","https://kyivindependent.com/api/v1/feed/full"),
 ("KI5","https://kyivindependent.com/feed"),
 ("VB1","https://venturebeat.com/feed/"),
 ("VB2","https://venturebeat.com/category/ai/feed"),
]
for tag,url in TRIES:
    try:
        r=requests.get(url,headers=UA,timeout=20,allow_redirects=True)
        n=len(feedparser.parse(r.content).entries)
        print("%-4s %-55s http=%-4s items=%s final=%s"%(tag,url,r.status_code,n,r.url[:70]))
    except Exception as e:
        print("%-4s %-55s ERR %s"%(tag,url,type(e).__name__))
    time.sleep(0.3)
