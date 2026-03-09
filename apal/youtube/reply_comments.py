#!/usr/bin/env python3
"""
APAL YouTube Comment Replier
=============================
Posts replies to YouTube comments using OAuth 2.0 authentication.

Setup (one-time):
  1. Go to https://console.cloud.google.com/
  2. Same project as fetch_comments.py
  3. Go to Credentials → Create → OAuth 2.0 Client ID
     - Application type: Desktop app
     - Download JSON → save as client_secret.json in this folder
  4. Go to OAuth consent screen → Add test user (your Google email)

Usage:
  # Interactive mode — prompts for each reply
  python3 reply_comments.py VIDEO_ID

  # Reply from a prepared CSV/JSON file
  python3 reply_comments.py --file replies.json

  replies.json format:
  [
    {"comment_id": "Ugw...", "reply": "Thanks for the feedback!"},
    {"comment_id": "Ugx...", "reply": "Great question! You can find..."}
  ]
"""

import sys
import os
import json
import argparse

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(SCRIPT_DIR, "token.json")
CLIENT_SECRET = os.path.join(SCRIPT_DIR, "client_secret.json")


def get_authenticated_service():
    """Authenticate with OAuth and return YouTube service."""
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CLIENT_SECRET):
                print(f"ERROR: {CLIENT_SECRET} not found!")
                print("\nTo create it:")
                print("  1. Go to https://console.cloud.google.com/apis/credentials")
                print("  2. Create OAuth 2.0 Client ID (Desktop app)")
                print("  3. Download JSON → save as client_secret.json here")
                sys.exit(1)

            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())
        print("Authentication successful! Token saved.\n")

    return build("youtube", "v3", credentials=creds)


def post_reply(youtube, parent_id, text):
    """Post a reply to a comment."""
    try:
        response = youtube.comments().insert(
            part="snippet",
            body={
                "snippet": {
                    "parentId": parent_id,
                    "textOriginal": text
                }
            }
        ).execute()
        return True, response["id"]
    except Exception as e:
        return False, str(e)


def interactive_mode(youtube, video_id):
    """Fetch comments and interactively reply."""
    from fetch_comments import fetch_all_comments, extract_video_id, categorize

    api_key = os.environ.get("YOUTUBE_API_KEY", "")
    if not api_key:
        print("Need YOUTUBE_API_KEY env var for fetching comments.")
        print("Set it: export YOUTUBE_API_KEY=YOUR_KEY")
        sys.exit(1)

    yt_read = build("youtube", "v3", developerKey=api_key)
    vid_id = extract_video_id(video_id)

    print(f"Fetching comments for {vid_id}...")
    comments = fetch_all_comments(yt_read, vid_id)

    # Filter to top-level, non-noise, sort by date (newest first)
    top_comments = [c for c in comments if not c['is_reply']]
    for c in top_comments:
        c['category'], c['intent'] = categorize(c['comment'])

    meaningful = [c for c in top_comments if c['category'] != 'Noise']
    meaningful.sort(key=lambda x: x['published'], reverse=True)

    print(f"\n{len(meaningful)} meaningful comments to review:\n")

    replied = []
    for i, c in enumerate(meaningful, 1):
        print(f"─── [{i}/{len(meaningful)}] {c['category']} ───")
        print(f"  Author:  {c['author']}")
        print(f"  Date:    {c['published'][:10]}")
        print(f"  Comment: {c['comment'][:200]}")
        print(f"  Intent:  {c['intent']}")
        print(f"  ID:      {c['comment_id']}")
        print()

        action = input("  [r]eply / [s]kip / [q]uit: ").strip().lower()
        if action == 'q':
            break
        elif action == 'r':
            reply_text = input("  Your reply: ").strip()
            if reply_text:
                ok, result = post_reply(youtube, c['comment_id'], reply_text)
                if ok:
                    print(f"  ✓ Reply posted! (ID: {result})")
                    replied.append({
                        'comment_id': c['comment_id'],
                        'author': c['author'],
                        'comment': c['comment'][:100],
                        'reply': reply_text
                    })
                else:
                    print(f"  ✗ Error: {result}")
        print()

    if replied:
        log_path = os.path.join(SCRIPT_DIR, f"replies_log_{vid_id}.json")
        with open(log_path, 'w', encoding='utf-8') as f:
            json.dump(replied, f, ensure_ascii=False, indent=2)
        print(f"\n{len(replied)} replies logged to: {log_path}")


def batch_mode(youtube, replies_file):
    """Post replies from a JSON file."""
    with open(replies_file) as f:
        replies = json.load(f)

    print(f"Posting {len(replies)} replies...\n")
    success = 0
    for r in replies:
        ok, result = post_reply(youtube, r['comment_id'], r['reply'])
        status = "✓" if ok else "✗"
        print(f"  {status} {r['comment_id'][:20]}... → {r['reply'][:50]}...")
        if ok:
            success += 1

    print(f"\nDone: {success}/{len(replies)} replies posted.")


def main():
    parser = argparse.ArgumentParser(description="Reply to YouTube comments")
    parser.add_argument("video", nargs="?", help="YouTube video URL or ID (interactive mode)")
    parser.add_argument("--file", help="JSON file with replies for batch mode")
    args = parser.parse_args()

    youtube = get_authenticated_service()

    if args.file:
        batch_mode(youtube, args.file)
    elif args.video:
        interactive_mode(youtube, args.video)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
