import json, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
FEEDS = [
 ("PC Gamer","https://www.pcgamer.com/rss/",["gaming","news"],2),
 ("Rock Paper Shotgun","https://www.rockpapershotgun.com/feed",["gaming","news"],2),
 ("Eurogamer","https://www.eurogamer.net/feed",["gaming","news"],2),
 ("GamesIndustry.biz","https://www.gamesindustry.biz/feed",["gaming","business"],2),
 ("VGC","https://www.videogameschronicle.com/feed/",["gaming","news"],2),
 ("GameSpot News","https://www.gamespot.com/feeds/news/",["gaming","news"],2),
 ("IGN Games","https://feeds.ign.com/ign/games-all",["gaming","news"],1),
 ("PCGamesN","https://www.pcgamesn.com/feed",["gaming","news"],1),
 ("Nintendo Life","https://www.nintendolife.com/feeds/latest",["gaming","news"],1),
 ("Push Square","https://www.pushsquare.com/feeds/latest",["gaming","news"],1),
 ("GamingOnLinux","https://www.gamingonlinux.com/article_rss.php",["gaming","linux"],1),
 ("Digital Foundry","https://feeds.feedburner.com/digitalfoundry",["gaming","tech"],2),
 ("Tom's Hardware","https://www.tomshardware.com/feeds/all",["hardware","tech"],2),
 ("TechPowerUp","https://www.techpowerup.com/rss/news",["hardware","tech"],1),
 ("Wccftech","https://wccftech.com/feed/",["hardware","tech"],1),
 ("The Register","https://www.theregister.com/headlines.atom",["tech","hardware"],1),
 ("The Verge AI","https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",["ai","tech"],2),
 ("Ars Technica","https://feeds.arstechnica.com/arstechnica/index",["tech","science"],2),
 ("TechCrunch AI","https://techcrunch.com/category/artificial-intelligence/feed/",["ai","tech"],2),
 ("MIT Technology Review","https://www.technologyreview.com/feed/",["tech","science"],1),
 ("Google AI Blog","https://blog.google/technology/ai/rss/",["ai","tech"],1),
 ("Hugging Face Blog","https://huggingface.co/blog/feed.xml",["ai","tech"],1),
 ("Game Developer","https://www.gamedeveloper.com/rss.xml",["gaming","business"],2),
 ("Kyiv Independent","https://kyivindependent.com/news-archive/rss/",["ukraine","world"],1),
]
out=[{"name":n,"url":u,"tags":t,"enabled":True,"weight":w} for n,u,t,w in FEEDS]
with open("config/feeds.json","w",encoding="utf-8") as f:
    json.dump(out,f,indent=2,ensure_ascii=False)
    f.write("\n")
print("wrote",len(out),"feeds")
