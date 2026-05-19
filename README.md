# BL/GL TMDB Auto Feed Generator

This project generates **two separate RSS feeds** for BL and GL content using the TMDB API.  
It supports **TV shows + movies**, uses **keywords + genres + country prioritization**, and integrates with **Wei Wei**, a custom Discord bot.

## ✨ Features

### ✔ TMDB-powered discovery
- Searches TV + Movies
- Uses BL/GL keyword sets
- Prioritizes 9 major BL/GL-producing countries:
  TH, JP, KR, CN, TW, PH, VN, HK, MY
- Still includes global titles

### ✔ Clean status classification
TMDB → Feed status:
- Returning Series → ongoing  
- In Production / Planned / Post Production / Pilot → upcoming  
- Ended → excluded  
- Canceled → excluded  

### ✔ Dual RSS feeds
Generated files:
- `feed_bl.xml` — BL-only feed  
- `feed_gl.xml` — GL-only feed  

Each feed includes:
- Poster  
- Country  
- Episode count  
- Next episode number  
- Next episode date  
- Synopsis  
- TMDB link  
- Countdown-ready metadata  

### ✔ Blacklist integration
Wei Wei maintains: data/blacklist.json

Format:
```json
{
  "BL": ["title1", "title2"],
  "GL": ["title3"]
}``` 

###The TMDB scraper automatically excludes blacklisted titles.

✔ State tracking
To prevent duplicate Discord posts:

state_bl.json

state_gl.json

Only changed items trigger Discord embeds.

✔ Discord posting
Two webhooks:

DISCORD_WEBHOOK_BL

DISCORD_WEBHOOK_GL

Each feed posts to its own channel.

✔ GitHub Actions automation
Runs every 6 minutes:

Fetches TMDB data

Applies blacklist

Builds feeds

Updates state

Posts to Discord

Commits updated XML + JSON

🔧 Setup
1. Environment variables
Set in GitHub Actions secrets:

```TMDB_API_KEY=your_key_here
DISCORD_WEBHOOK_BL=...
DISCORD_WEBHOOK_GL=...```

2. Blacklist file
Create: data/blacklist.json
With:
```{
  "BL": [],
  "GL": []
}```

3. Install dependencies
```pip install -r requirements.txt```

4. Run manually
```python update.py```

GitHub Actions
Workflow commits:

```feed_bl.xml

feed_gl.xml

state_bl.json

state_gl.json```

📁 File Structure
```update.py
tmdb_fetcher.py
rss_builder.py
rss_parser.py
state_manager.py
post_to_discord.py
data/
   blacklist.json
feed_bl.xml
feed_gl.xml
state_bl.json
state_gl.json```

🧩 Integration with Wei Wei
Wei Wei provides:

/blacklist-add

/blacklist-remove

/blacklist-list

These commands update data/blacklist.json.
The TMDB scraper respects it automatically.
