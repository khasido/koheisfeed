# bl-rss
Ongoing and upcoming boys love drama RSS feed scraped from my drama list, list manually updated; feed auto updates using every 6 hour cron job.

## Setup

Install the runtime dependencies with the repository virtual environment:

```powershell
cd C:\Users\khasi\OneDrive\Repos\bl-rss
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Then run the updater using the repo venv Python. If the venv is activated, use:

```powershell
cd C:\Users\khasi\OneDrive\Repos\bl-rss
python update.py
```

If you have not activated the venv, run the script directly with the repo interpreter:

```powershell
cd C:\Users\khasi\OneDrive\Repos\bl-rss
.\.venv\Scripts\python.exe .\update.py
```

Alternatively, use the provided launcher script from the repo root:

PowerShell:
```powershell
cd C:\Users\khasi\OneDrive\Repos\bl-rss
.\run.ps1
```

Command Prompt:
```cmd
cd C:\Users\khasi\OneDrive\Repos\bl-rss
run.cmd
```

> If you see a message about `C:\Users\khasi\AppData\Local\Programs\Python\Python313\python.exe`, that means the global Python install is being used instead of the repository virtual environment.
