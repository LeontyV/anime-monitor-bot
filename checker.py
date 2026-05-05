#!/usr/bin/env python3
"""
Anime Monitor - Checks for new episodes and sends notifications.
Run this via cron every 30 minutes.

FIX: Uses get_full_episode_info() from parser.py (same as bot.py),
NOT soup.get_text() from entire page (which picked up stale data from
recommendation blocks and caused DB values to be overwritten incorrectly).
"""

import psycopg2
import os
import sys
import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import get_monitored_anime, add_anime, mark_notified
from parser import get_full_episode_info, get_episode_list, get_video_url

load_dotenv()

VOST_URL = os.getenv('VOST_URL', 'https://v13.vost.pw/tip/tv/')
TELEGRAM_TOKEN = os.getenv('TOKEN')
ALLOWED_USER_ID = int(os.getenv('ALLOWED_USER_ID', '68650276'))


def build_url(vost_url):
    """Build full URL from relative path."""
    if vost_url.startswith('http'):
        return vost_url
    base = VOST_URL.rstrip('/')
    return f"{base}{vost_url}"


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
    """Check for new episodes of monitored anime.
    
    Uses get_full_episode_info() — same parsing as bot.py (shortstory div only,
    server-time countdown). Previous implementation used soup.get_text() on the
    entire page which incorrectly picked up next_episode_date from recommendation
    blocks ("Последние обновления") on the same page.
    """
    monitored = get_monitored_anime()

    if not monitored:
        print("No anime in monitoring list.")
        return

    print(f"Checking {len(monitored)} anime titles...")

    for anime in monitored:
        try:
            # Use the SAME parser function as bot.py — parses shortstory div only
            info = get_full_episode_info(anime['vost_url'])

            if not info or not info.get('title_ru'):
                print(f"⚠️ {anime['title_ru']}: could not parse info from Vost")
                continue

            current_episode = info['current_episode']
            total_episodes = info['total_episodes']
            next_episode_date = info['next_episode_date']
            next_episode_time = info['next_episode_time']

            # Check if there's a new episode
            if current_episode > anime['current_episode']:
                new_ep = current_episode

                # Get video URL for the new episode
                video_link = ""
                try:
                    episodes = get_episode_list(anime['vost_url'])
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

                # Update database with new episode info
                add_anime(
                    anime['title_ru'],
                    anime['title_en'],
                    anime['vost_url'],
                    current_episode,
                    total_episodes,
                    next_episode_date,
                    next_episode_time
                )
            else:
                print(f"⏸ {anime['title_ru']}: No new episodes ({anime['current_episode']} == {current_episode})")

            # If next_episode_date changed, update it quietly
            # Preserve old values when parser returns None (countdown expired / not yet updated)
            if not next_episode_date and anime.get('next_episode_date'):
                next_episode_date = anime['next_episode_date']
            if not next_episode_time and anime.get('next_episode_time'):
                next_episode_time = anime['next_episode_time']

            if next_episode_date != anime.get('next_episode_date'):
                add_anime(
                    anime['title_ru'],
                    anime['title_en'],
                    anime['vost_url'],
                    anime['current_episode'],
                    total_episodes,
                    next_episode_date,
                    next_episode_time
                )

        except Exception as e:
            print(f"❌ Error checking {anime['title_ru']}: {e}")

if __name__ == '__main__':
    check_new_episodes()
