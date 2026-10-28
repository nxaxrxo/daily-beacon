import json, sys, time
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import feedparser, requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5"}

CANDS = [
 ("PC Gamer", "https://www.pcgamer.com/rss/", ["gaming","news"], 2),
 ("Rock Paper Shotgun", "https://www.rockpapershotgun.com/feed", ["gaming","news"], 2),
 ("Eurogamer", "https://www.eurogamer.net/feed", ["gaming","news"], 2),
 ("GamesIndustry.biz", "https://www.gamesindustry.biz/feed", ["gaming","business"], 2),
 ("VGC", "https://www.videogameschronicle.com/feed/", ["gaming","news"], 2),
 ("GameSpot News", "https://www.gamespot.com/feeds/news/", ["gaming","news"], 2),
 ("IGN", "https://feeds.ign.com/ign/games-all", ["gaming","news"], 1),
 ("Digital Foundry", "https://www.eurogamer.net/digitalfoundry/rss", ["gaming","tech"], 2),
 ("Tom's Hardware", "https://www.tomshardware.com/feeds/all", ["hardware","tech"], 2),
 ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", ["ai","tech"], 2),
 ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index", ["tech","science"], 2),
 ("Ars Technica AI", "https://feeds.arstechnica.com/arstechnica/technology-lab", ["ai","tech"], 1),
 ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/", ["ai","tech"], 2),
 ("VentureBeat AI", "https://venturebeat.com/category/ai/feed/", ["ai","business"], 1),
 ("MIT Technology Review", "https://www.technologyreview.com/feed/", ["tech","science"], 1),
 ("Game Developer", "https://www.gamedeveloper.com/rss.xml", ["gaming","business"], 2),
 ("Kyiv Independent", "https://kyivindependent.com/api/v1/feed", ["ukraine","world"], 1),
 ("PCGamesN", "https://www.pcgamesn.com/feed", ["gaming","news"], 1),
 ("Nintendo Life", "https://www.nintendolife.com/feeds/latest", ["gaming","news"], 1),
 ("Push Square", "https://www.pushsquare.com/feeds/latest", ["gaming","news"], 1),
 ("Wccftech", "https://wccftech.com/feed/", ["hardware","tech"], 1),
 ("TechPowerUp", "https://www.techpowerup.com/rss/news", ["hardware","tech"], 1),
 ("Hugging Face Blog", "https://huggingface.co/blog/feed.xml", ["ai","tech"], 1),
 ("Google AI Blog", "https://blog.google/technology/ai/rss/", ["ai","tech"], 1),
 ("OpenAI Blog", "https://openai.com/news/rss.xml", ["ai","tech"], 1),
 ("GamingOnLinux", "https://www.gamingonlinux.com/article_rss.php", ["gaming","linux"], 1),
 ("Dexerto", "https://www.dexerto.com/feed/", ["gaming","news"], 1),
 ("Kotaku", "https://kotaku.com/rss", ["gaming","news"], 1),
 ("TheGamer", "https://www.thegamer.com/feed/", ["gaming","news"], 1),
 ("Engadget", "https://www.engadget.com/rss.xml", ["tech","hardware"], 1),
 ("Ukrainska Pravda", "https://www.pravda.com.ua/rss/", ["ukraine","world"], 1),
 ("The Register", "https://www.theregister.com/headlines.atom", ["tech","hardware"], 1),
]

out = []
for name, url, tags, weight in CANDS:
    rec = {"name": name, "url": url, "tags": tags, "weight": weight}
    code = None
    n = 0
    err = None
    try:
        r = requests.get(url, headers=UA, timeout=20)
        code = r.status_code
        if code == 200:
            fd = feedparser.parse(r.content)
            n = len(fd.entries)
            if n == 0 and getattr(fd, "bozo", 0):
                err = str(getattr(fd, "bozo_exception", ""))[:100]
    except Exception as e:
        err = type(e).__name__ + ": " + str(e)[:100]
    rec["http"] = code
    rec["items"] = n
    rec["error"] = err
    out.append(rec)
    print("%-24s http=%-5s items=%-3s %s" % (name, code, n, err or ""))
    time.sleep(0.3)

json.dump(out, open("state/_feedcheck/probe.json", "w", encoding="utf-8"), indent=1)
print("PROBE DONE", len(out))
