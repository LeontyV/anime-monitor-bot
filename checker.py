#!/usr/bin/env python3
"""
Anime Monitor - Checks for new episodes and sends notifications.
Run this via cron every 30 minutes.
"""

import psycopg2
import os
import sys
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import get_db_connection, get_monitored_anime, add_anime, mark_notified
from parser import get_episode_list, get_video_url

load_dotenv()

VOST_URL = os.getenv('VOST_URL', 'https://v13.vost.pw/tip/tv/')
TELEGRAM_TOKEN = os.getenv('TOKEN')

def build_url(vost_url):
    """Build full URL from relative path."""
    if vost_url.startswith('http'):
        return vost_url
    base = VOST_URL.rstrip('/')
    return f"{base}{vost_url}"
ALLOWED_USER_ID = 68650276

def send_telegram_message(chat_id, text):
    """Send message via Telegram bot."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'Markdown',
        'disable_web_page_preview': True
    }
    requests.post(url, data=data)

def check_new_episodes():
    """Check for new episodes of monitored anime."""
    monitored = get_monitored_anime()
    
    if not monitored:
        print("No anime in monitoring list.")
        return
    
    print(f"Checking {len(monitored)} anime titles...")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    for anime in monitored:
        try:
            response = requests.get(build_url(anime['vost_url']), headers=headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            text = soup.get_text()
            
            # Look for patterns like [1-207 из 208] or [1-4 из 12+]
            # Format: [min-max из total extra]
            episode_pattern = r'\[(\d+)-(\d+)[\sиз]*([^\]]*)\]'
            match = re.search(episode_pattern, text)
            
            if match:
                current_episode = int(match.group(2))  # max available
                total = match.group(2)
                extra = match.group(3).strip()
                # Use group(3) for total_episodes if it has content, else group(2)
                total_episodes = extra if extra else total
                
                # Check if there's a new episode
                if current_episode > anime['current_episode']:
                    new_ep = current_episode
                    
                    # Get video URL for the new episode
                    video_link = ""
                    try:
                        episodes = get_episode_list(anime['vost_url'])
                        # Find the episode that corresponds to new_ep
                        ep_name = f"{new_ep} серия"
                        for ep in episodes:
                            if ep['episode'] == ep_name:
                                video_url = get_video_url(ep['play_id'])
                                if video_url:
                                    video_link = f"\n\n[▶ Смотреть видео]({video_url})"
                                break
                    except Exception as e:
                        print(f"⚠️ Could not get video URL: {e}")

                    # Send notification
                    title = anime['title_ru']
                    message = (
                        f"🆕 *Новая серия!*\n\n"
                        f"*{title}*\n"
                        f"Серия {new_ep} из {total_episodes}"
                        f"{video_link}\n\n"
                        f"[Смотреть на Vost]({build_url(anime['vost_url'])})"
                    )
                    
                    try:
                        send_telegram_message(ALLOWED_USER_ID, message)
                        mark_notified(anime['id'], new_ep)
                        print(f"✅ Notified: {title} - Episode {new_ep}")
                    except Exception as e:
                        print(f"❌ Failed to notify about {title}: {e}")
                    
                    # Update database
                    add_anime(
                        anime['title_ru'],
                        anime['title_en'],
                        anime['vost_url'],
                        current_episode,
                        total_episodes,
                        anime['next_episode_date'],
                        anime['next_episode_time']
                    )
                else:
                    print(f"⏸ {anime['title_ru']}: No new episodes ({anime['current_episode']} == {current_episode})")
            
            # Also check for next episode date in text
            next_pattern = r'\[(\d+)[\sсерия]*-\s*(\d+\s+\S+)\]'
            match = re.search(next_pattern, text)
            if match:
                next_episode = int(match.group(1))
                next_date = match.group(2)
                # Update next episode info
                if next_episode > anime['current_episode']:
                    conn = get_db_connection()
                    cur = conn.cursor()
                    cur.execute("""
                        UPDATE anime_list 
                        SET next_episode_date = %s, updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, (next_date, anime['id']))
                    conn.commit()
                    cur.close()
                    conn.close()
        
        except Exception as e:
            print(f"❌ Error checking {anime['title_ru']}: {e}")

if __name__ == '__main__':
    check_new_episodes()
