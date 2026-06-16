# movie-xray-mcp

A [FastMCP](https://github.com/jlowin/fastmcp) server that gives Claude an Amazon Prime
"X-Ray"-style view of movies and TV shows: look up a title, see the cast, drill into an
actor's bio and filmography, find out what else of theirs is on Netflix right now, and
link out to IMDb for more detail.

Ask Claude things like:
- *"Search for The Matrix and tell me about the cast"*
- *"Who plays Neo, and what else has Keanu Reeves been in?"*
- *"Is anything from Keanu Reeves' filmography on Netflix right now?"*
- *"What's the IMDb rating and Rotten Tomatoes score for Oppenheimer?"*
- *"Show me everything streaming for The Bear, with cast and IMDb links"*

---

## Tools

| Tool | Description | Auth required |
|------|-------------|---------------|
| `search_title` | Search for a movie or TV show | No |
| `get_title_details` | Synopsis, cast, ratings, IMDb link, and streaming availability | No |
| `get_actor_info` | Actor bio, photo, and IMDb link | No |
| `get_actor_filmography` | An actor's filmography, sorted by popularity | No |
| `get_watch_providers` | Where a title is streaming/renting/buying (incl. Netflix) | No |
| `get_actor_netflix_titles` | Cross-references an actor's filmography against Netflix's catalog | No |

Everything here uses public catalog data — no Spotify-style OAuth login is needed.

---

## Prerequisites

- **Python 3.10+** (required by FastMCP and the underlying MCP SDK — see below if you're not sure what you have)
- A free [TMDb](https://www.themoviedb.org/) account and API key
- A free [OMDb](https://www.omdbapi.com/) API key (optional — adds IMDb/Rotten
  Tomatoes/Metacritic ratings and plot text to `get_title_details`)

### Checking your Python version

```bash
python3 --version
```

If this prints `3.10.x`, `3.11.x`, `3.12.x`, or `3.13.x`, you're good — skip to Step 1.

If it prints `3.9.x` or lower (common on macOS, which ships an old system Python),
you need to install a newer Python **before** creating the virtual environment in
Step 3. `pip install -r requirements.txt` will fail with
`Could not find a version that satisfies the requirement fastmcp>=2.0` if you try to
use Python 3.9 or earlier.

#### Installing Python 3.10+

**macOS (Homebrew):**
```bash
brew install python@3.12
```
This installs a separate `python3.12` binary alongside your system Python — it won't
replace or break anything else. Verify with:
```bash
python3.12 --version
```

**macOS (no Homebrew):** Download the installer from
[python.org/downloads](https://www.python.org/downloads/) and run it. After
installing, use `python3.12` (or whichever version you installed) in place of
`python3` below.

**Windows:** Download the installer from
[python.org/downloads](https://www.python.org/downloads/), run it, and check
**"Add python.exe to PATH"** during install. Verify with:
```powershell
python --version
```

**Linux (Debian/Ubuntu):**
```bash
sudo apt update
sudo apt install python3.12 python3.12-venv
```

**Using pyenv (any OS, if you manage multiple Python versions):**
```bash
pyenv install 3.12.7
pyenv local 3.12.7   # sets this version for the movie-xray-mcp directory
```

Once you have a 3.10+ interpreter available, use **that** binary (e.g. `python3.12`)
instead of `python3` when creating the virtual environment in Step 3.

---

## Step 1: Get a TMDb API key

1. Create a free account at [themoviedb.org](https://www.themoviedb.org/signup)
2. Go to **Settings → API** ([themoviedb.org/settings/api](https://www.themoviedb.org/settings/api))
3. Request an API key (choose "Developer" — instant approval for personal use)
4. Copy the **API Key (v3 auth)** value

---

## Step 2: Get an OMDb API key (optional)

1. Go to [omdbapi.com/apikey.aspx](https://www.omdbapi.com/apikey.aspx)
2. Select the free tier and enter your email
3. Activate the key via the email OMDb sends you

If you skip this, `get_title_details` still works — it just won't include the
`ratings` field (IMDb rating, Rotten Tomatoes, Metascore, plot, etc.).

---

## Step 3: Local Setup

```bash
cd movie-xray-mcp

# Create virtual environment using Python 3.10+
# If `python3 --version` showed 3.10+, use python3 below.
# Otherwise, substitute the 3.10+ binary you installed above (e.g. python3.12).
python3 -m venv .venv
source .venv/bin/activate        # Mac/Linux
# .venv\Scripts\activate         # Windows

# Confirm the venv is using Python 3.10+
python --version

# Install dependencies
pip install -r requirements.txt

# Copy env template and fill in your keys
cp .env.example .env
```

If `pip install -r requirements.txt` fails with
`Could not find a version that satisfies the requirement fastmcp>=2.0`, your venv was
created with Python <3.10. Delete it and recreate using a 3.10+ binary:

```bash
rm -rf .venv
python3.12 -m venv .venv   # use whichever 3.10+ binary you installed
source .venv/bin/activate
pip install -r requirements.txt
```

Edit `.env`:
```env
TMDB_API_KEY=your_tmdb_v3_api_key_here
OMDB_API_KEY=your_omdb_api_key_here
DEFAULT_REGION=US
```

`DEFAULT_REGION` is an ISO 3166-1 country code used by default for streaming
availability (e.g. `US`, `GB`, `CA`). It can be overridden per-call on any tool that
takes a `region` argument.

---

## Step 4: Run Locally

### Option A: stdio (for Claude Desktop)
```bash
python server.py
# or explicitly:
python server.py stdio
```

### Option B: SSE (for Railway / remote clients)
```bash
python server.py sse
# Server starts on http://localhost:8000
```

---

## Step 5: Connect to Claude Desktop

Add this to your Claude Desktop config file:

**Mac:** `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "movie-xray-mcp": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["/absolute/path/to/movie-xray-mcp/server.py"],
      "env": {
        "TMDB_API_KEY": "your_tmdb_v3_api_key_here",
        "OMDB_API_KEY": "your_omdb_api_key_here",
        "DEFAULT_REGION": "US"
      }
    }
  }
}
```

Replace `/absolute/path/to/` with your actual paths.

Restart Claude Desktop after saving. You should see `movie-xray-mcp` in the tools list.

---

## Step 6: Deploy to Railway

### First-time setup
```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Initialize project
railway init

# Set environment variables
railway variables set TMDB_API_KEY=your_tmdb_v3_api_key_here
railway variables set OMDB_API_KEY=your_omdb_api_key_here
railway variables set DEFAULT_REGION=US
```

### Deploy
```bash
railway up
```

Railway reads `railway.toml` and automatically:
- Detects Python via Nixpacks
- Installs `requirements.txt`
- Runs `python server.py sse`
- Sets `PORT` environment variable

### Get your deployed URL
```bash
railway domain
# Returns something like: https://movie-xray-mcp-production.up.railway.app
```

### Connect Claude to your Railway deployment
Once deployed, your MCP server is accessible via SSE at:
```
https://your-app.railway.app/sse
```

Add this to your Claude Desktop config:
```json
{
  "mcpServers": {
    "movie-xray-mcp": {
      "url": "https://your-app.railway.app/sse"
    }
  }
}
```

---

## Project Structure

```
movie-xray-mcp/
├── server.py          # FastMCP server — all tools live here
├── requirements.txt   # Python dependencies
├── railway.toml       # Railway deployment config
├── .env.example       # Environment variable template
├── .env               # Your actual API keys (gitignored)
└── README.md          # This file
```

---

## Example Prompts for Claude

Once connected, try these:

```
Search for "The Bear" and give me an overview.

Who's in the cast of Oppenheimer, and what are their IMDb pages?

What's the IMDb rating, Rotten Tomatoes score, and plot summary for Dune: Part Two?

Tell me about Zendaya — bio, IMDb link, and her most popular roles.

Is anything from Pedro Pascal's filmography currently on Netflix in the US?

Where can I stream The Matrix — is it on Netflix?
```

---

## Notes on Rate Limits & Performance

- **TMDb**: generous free-tier limits, suitable for personal/demo use.
- **OMDb**: free tier is limited to 1,000 requests/day. `get_title_details` only calls
  OMDb once per title (and skips it entirely if `OMDB_API_KEY` isn't set or the IMDb ID
  can't be resolved).
- **`get_actor_netflix_titles`**: checks the actor's `top_n` most popular credits
  (default 15) against Netflix's catalog for `region`. Each credit checked is one extra
  TMDb call, so raising `top_n` trades speed for completeness — most users only care
  about an actor's well-known work, which `top_n=15` already covers.

---

## Architecture Notes

- **TMDb** (themoviedb.org) powers search, cast/crew, filmographies, IMDb ID
  resolution, and `watch/providers` (JustWatch-sourced streaming availability,
  including Netflix, by region).
- **OMDb** (omdbapi.com) optionally enriches title details with IMDb/Rotten
  Tomatoes/Metacritic ratings and plot text.
- FastMCP handles the MCP protocol — all tools are decorated with `@mcp.tool()`.
- Transport is switchable: `stdio` for local/Claude Desktop, `sse` for Railway/remote.
- Railway auto-detects Python via Nixpacks — no Dockerfile needed.

---

## Built With

- [FastMCP](https://github.com/jlowin/fastmcp) — MCP server framework
- [TMDb API](https://developer.themoviedb.org/) — movie/TV metadata, cast, and streaming availability
- [OMDb API](https://www.omdbapi.com/) — IMDb/Rotten Tomatoes/Metacritic ratings
- [Railway](https://railway.app) — deployment platform
