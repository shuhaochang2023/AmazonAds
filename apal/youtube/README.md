# APAL YouTube Comment Tools

## Quick Setup (5 min)

### 1. Get YouTube API Key (for reading comments)
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project or select existing
3. Search **"YouTube Data API v3"** → Enable it
4. Go to **Credentials** → **Create Credentials** → **API Key**
5. Copy the key

### 2. Get OAuth Client (for posting replies)
1. Same project → **Credentials** → **Create Credentials** → **OAuth 2.0 Client ID**
2. Application type: **Desktop app**
3. Download JSON → rename to `client_secret.json` → put in this folder
4. Go to **OAuth consent screen** → add your Google email as test user

## Usage

```bash
# Set your API key
export YOUTUBE_API_KEY="AIza..."

# Fetch & categorize all comments → Excel
python3 fetch_comments.py "https://www.youtube.com/watch?v=X4q7l_8pQHg"

# Compare with previous export to highlight NEW comments
python3 fetch_comments.py X4q7l_8pQHg --diff APAL_Comments_previous.xlsx

# Also save raw JSON
python3 fetch_comments.py X4q7l_8pQHg --json

# Interactive reply mode (requires client_secret.json)
python3 reply_comments.py X4q7l_8pQHg

# Batch reply from file
python3 reply_comments.py --file replies.json
```

## Output
- `APAL_Comments_{videoId}_{timestamp}.xlsx` — categorized comments with:
  - **Summary** tab — counts per category
  - **Core_Strengths** — positive sentiment
  - **Business_Opportunities** — purchase intent, use cases
  - **Competitor_Comparisons** — mentions of other products
  - **Pain_Points** — criticism, issues
  - **All_Comments** — everything color-coded
  - NEW comments highlighted in yellow when using `--diff`

## Files
- `fetch_comments.py` — read-only, uses API key
- `reply_comments.py` — read+write, uses OAuth
- `client_secret.json` — your OAuth credentials (DO NOT COMMIT)
- `token.json` — auto-generated auth token (DO NOT COMMIT)
