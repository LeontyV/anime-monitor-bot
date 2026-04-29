import requests
from bs4 import BeautifulSoup
import re
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
    
    # Parse "Последние обновления" section
    updates_header = soup.find(string=re.compile('Последние обновления'))
    if updates_header:
        updates_div = updates_header.find_parent('div')
        if updates_div:
            for link in updates_div.find_all('a', href=True):
                href = link.get('href')
                if '/tip/tv/' in href and href.endswith('.html'):
                    title = link.get_text(strip=True)
                    if title and not title.startswith('http'):
                        anime_list.append({
                            'title': title,
                            'url': href,
                            'type': 'updates'
                        })
    
    # Parse "Расписание" section
    schedule_header = soup.find(string=re.compile('Расписание'))
    if schedule_header:
        schedule_div = schedule_header.find_parent('div')
        if schedule_div:
            for link in schedule_div.find_all('a', href=True):
                href = link.get('href')
                if '/tip/tv/' in href and href.endswith('.html'):
                    title = link.get_text(strip=True)
                    if title and not title.startswith('http'):
                        time = parse_schedule_time(title)
                        anime_list.append({
                            'title': title.replace('~', '').strip(),
                            'url': href,
                            'type': 'schedule',
                            'time': time
                        })
    
    return anime_list

def get_full_episode_info(url):
    """Get detailed episode info from anime page."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
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
            current_episode = int(match.group(1))
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

if __name__ == '__main__':
    anime_list = fetchAnimeList()
    for anime in anime_list[:5]:
        print(f"{anime['title']} - {anime['url']}")
