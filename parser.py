import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

VOST_URL = os.getenv('VOST_URL')

def parse_episode_info(text):
    """Parse episode info like '[1-207 из 208] [208 серия - 23 апреля]'."""
    current = 0
    total = None
    next_date = None
    next_time = None
    
    # Pattern: [1-207 из 208] or [1-3 из 12+]
    episode_pattern = r'\[(\d+)-(\d+)[\sиз]*([^\]]*)\]'
    match = re.search(episode_pattern, text)
    if match:
        current = int(match.group(1))
        total = match.group(2) + match.group(3).strip()
    
    # Pattern: [208 серия - 23 апреля] or [3 серия - 22 апреля]
    next_pattern = r'\[(\d+)[\sсерия]*-\s*(\d+\s+\S+)'
    match = re.search(next_pattern, text)
    if match:
        next_episode = int(match.group(1))
        next_date = match.group(2)
        # If we found next episode info, update current
        if next_episode > current:
            current = next_episode - 1
    
    return current, total, next_date, next_time

def parse_schedule_time(text):
    """Parse time from schedule like '~ (18:30)' or '~ (В течение дня)'."""
    time_pattern = r'~\s*\((\d+:\d+)\)'
    match = re.search(time_pattern, text)
    if match:
        return match.group(1)
    
    if 'В течение дня' in text:
        return 'day'
    
    return None

def fetchAnimeList():
    """Fetch anime list from Vost."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    response = requests.get(VOST_URL, headers=headers, timeout=30)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, 'html.parser')
    
    anime_list = []
    
    day_ids = ['raspisMon', 'raspisTue', 'raspisWed', 'raspisThu', 'raspisFri', 'raspisSat', 'raspisSun']
    day_names = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
    
    for day_name, day_id in zip(day_names, day_ids):
        div = soup.find('div', id=day_id)
        if div:
            links = div.find_all('a', href=True)
            for link in links:
                href = link.get('href')
                if '/tip/tv/' in href and href.endswith('.html'):
                    title = link.get_text(strip=True).replace('~', '').strip()
                    if title and not title.startswith('http'):
                        time = parse_schedule_time(link.get_text(strip=True))
                        anime_list.append({
                            'title': title,
                            'url': href,
                            'type': 'schedule',
                            'day': day_name,
                            'time': time
                        })
    
    return anime_list

def get_full_episode_info(url):
    """Get detailed episode info from anime page."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    # Handle relative URLs
    if url.startswith('/'):
        base = os.getenv('VOST_URL', 'https://v13.vost.pw/tip/tv/')
        base = base.rstrip('/')
        if base.endswith('/tip/tv'):
            base = base.rsplit('/tip/tv', 1)[0]
        url = base + url
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Find episode info in the page
        text = soup.get_text()
        
        # Look for patterns like [1-207 из 208] or [1-3 из 12+]
        episode_pattern = r'\[(\d+)-(\d+)[\sиз]*([^\]]*)\]'
        match = re.search(episode_pattern, text)
        
        current_episode = 0
        total_episodes = None
        
        if match:
            # [X-Y из Z] means episodes X through Y are available, latest is Y
            current_episode = int(match.group(2))  # Y is the latest available
            total = match.group(2)
            extra = match.group(3).strip()
            total_episodes = f"{total} {extra}" if extra else total
        
        # Look for next episode date: [208 серия - 23 апреля]
        next_pattern = r'\[(\d+)[\sсерия]*-\s*(\d+\s+\S+)\]'
        match = re.search(next_pattern, text)
        next_date = None
        if match:
            next_date = match.group(2)
        
        # Get title
        title_ru = None
        title_en = None
        
        title_tag = soup.find('h1')
        if title_tag:
            full_title = title_tag.get_text(strip=True)
            # Split by slash to get ru/en titles
            if '/' in full_title:
                parts = full_title.split('/')
                title_ru = parts[0].strip()
                title_en = parts[1].strip() if len(parts) > 1 else None
            else:
                title_ru = full_title
        
        return {
            'title_ru': title_ru,
            'title_en': title_en,
            'current_episode': current_episode,
            'total_episodes': total_episodes,
            'next_episode_date': next_date
        }
    except Exception as e:
        print(f"Error fetching {url}: {e}")
        return None

def get_video_url(play_id):
    """Fetch frame5.php and extract 720p video URL for a given play_id."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    frame_url = f"https://v13.vost.pw/frame5.php?play={play_id}&player=9"
    try:
        response = requests.get(frame_url, headers=headers, timeout=30)
        response.raise_for_status()
        text = response.text

        # 720p URL is directly in HTML: <a href="https://vn5614.tigerlips.org/720/{play_id}.mp4?md5=...">
        pattern = rf'/720/{re.escape(play_id)}\.mp4\?md5=[^<"]+'
        match = re.search(pattern, text)
        if match:
            return 'https://vn5614.tigerlips.org' + match.group()
        return None

    except Exception as e:
        print(f"Error getting video URL for {play_id}: {e}")
        return None


def get_episode_list(url):
    """Extract episode IDs and names from anime page.
    Returns list of {episode: str (e.g. "1 серия"), play_id: str}
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }

    if url.startswith('/'):
        base = os.getenv('VOST_URL', 'https://v13.vost.pw/tip/tv/')
        base = base.rstrip('/')
        if base.endswith('/tip/tv'):
            base = base.rsplit('/tip/tv', 1)[0]
        url = base + url

    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find inline JS data like: {"1 серия":"2147411208","2 серия":"2147411298",...}
        pattern = r'var i = 0;\s*var data = (\{.*?\});'
        match = re.search(pattern, response.text, re.DOTALL)
        if not match:
            return []

        raw_data = match.group(1)
        # Strip trailing comma before } to make valid JSON
        raw_data = re.sub(r',\}$', '}', raw_data)
        data = json.loads(raw_data)

        episodes = []
        for ep_name, play_id in data.items():
            episodes.append({
                'episode': ep_name,
                'play_id': play_id
            })
        return episodes
    except Exception as e:
        print(f"Error fetching episodes from {url}: {e}")
        return []


if __name__ == '__main__':
    SCHEDULE_ITEMS_LIMIT = int(os.getenv('SCHEDULE_ITEMS_LIMIT', '5'))
    anime_list = fetchAnimeList()
    for anime in anime_list[:SCHEDULE_ITEMS_LIMIT]:
        print(f"{anime['title']} - {anime['url']}")
