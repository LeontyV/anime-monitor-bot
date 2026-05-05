import psycopg2
from psycopg2.extras import RealDictCursor
import os
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()


@contextmanager
def _db(cursor_factory=None):
    """Database connection context manager with automatic commit/rollback."""
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST'),
        port=os.getenv('DB_PORT'),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASS')
    )
    try:
        cur = conn.cursor(cursor_factory=cursor_factory) if cursor_factory else conn.cursor()
        yield conn, cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def _execute(query, params=None, fetch=None, cursor_factory=None):
    """Helper to execute a query with optional fetch."""
    with _db(cursor_factory=cursor_factory) as (conn, cur):
        cur.execute(query, params)
        if fetch == 'all':
            return cur.fetchall()
        elif fetch == 'one':
            return cur.fetchone()
        return None


def init_db():
    """Create tables if they don't exist."""
    with _db() as (conn, cur):
        cur.execute("""
            CREATE TABLE IF NOT EXISTS anime_list (
                id SERIAL PRIMARY KEY,
                title_ru TEXT NOT NULL,
                title_en TEXT,
                vost_url TEXT UNIQUE NOT NULL,
                current_episode INTEGER DEFAULT 0,
                total_episodes TEXT,
                next_episode_date TEXT,
                next_episode_time TEXT,
                notified INTEGER DEFAULT 0,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS parse_history (
                id SERIAL PRIMARY KEY,
                parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                new_episodes_found INTEGER DEFAULT 0
            )
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id SERIAL PRIMARY KEY,
                anime_id INTEGER REFERENCES anime_list(id),
                episode INTEGER,
                notified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                message_sent BOOLEAN DEFAULT FALSE
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS anime_episodes (
                id SERIAL PRIMARY KEY,
                anime_id INTEGER REFERENCES anime_list(id) ON DELETE CASCADE,
                play_id TEXT NOT NULL,
                episode_name TEXT NOT NULL,
                url TEXT NOT NULL,
                file_id TEXT,
                UNIQUE(anime_id, play_id)
            )
        """)


def add_anime(title_ru, title_en, vost_url, current_episode, total_episodes, next_episode_date, next_episode_time):
    """Add or update anime in the monitoring list."""
    _execute("""
        INSERT INTO anime_list (title_ru, title_en, vost_url, current_episode, total_episodes, next_episode_date, next_episode_time, notified)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 0)
        ON CONFLICT (vost_url) DO UPDATE SET
            title_ru = EXCLUDED.title_ru,
            title_en = EXCLUDED.title_en,
            current_episode = EXCLUDED.current_episode,
            total_episodes = EXCLUDED.total_episodes,
            next_episode_date = EXCLUDED.next_episode_date,
            next_episode_time = EXCLUDED.next_episode_time,
            updated_at = CURRENT_TIMESTAMP,
            notified = 0
    """, (title_ru, title_en, vost_url, current_episode, total_episodes, next_episode_date, next_episode_time))


def get_monitored_anime():
    """Get all anime in the monitoring list."""
    return _execute("SELECT * FROM anime_list ORDER BY title_ru", fetch='all', cursor_factory=RealDictCursor)


def mark_notified(anime_id, episode):
    """Mark an episode as notified."""
    with _db() as (conn, cur):
        cur.execute("""
            INSERT INTO notifications (anime_id, episode, message_sent)
            VALUES (%s, %s, TRUE)
        """, (anime_id, episode))
        cur.execute("""
            UPDATE anime_list SET notified = 1, current_episode = %s WHERE id = %s
        """, (episode, anime_id))


def get_anime_by_url(vost_url):
    """Get anime by its Vost URL."""
    return _execute("SELECT * FROM anime_list WHERE vost_url = %s", (vost_url,), fetch='one', cursor_factory=RealDictCursor)


def remove_anime(anime_id):
    """Remove anime from monitoring list."""
    with _db() as (conn, cur):
        cur.execute("DELETE FROM notifications WHERE anime_id = %s", (anime_id,))
        cur.execute("DELETE FROM anime_list WHERE id = %s", (anime_id,))


def add_episodes(anime_id, episodes):
    """Add or update episodes for an anime.
    episodes: list of {episode: str, play_id: str, url: str}
    Only inserts new episodes (ON CONFLICT DO NOTHING).
    """
    with _db() as (conn, cur):
        for ep in episodes:
            cur.execute("""
                INSERT INTO anime_episodes (anime_id, play_id, episode_name, url)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (anime_id, play_id) DO NOTHING
            """, (anime_id, ep['play_id'], ep['episode'], ep.get('url', '')))


def update_episode_file_id(play_id, file_id):
    """Update file_id for an episode after uploading to Telegram."""
    _execute("""
        UPDATE anime_episodes SET file_id = %s WHERE play_id = %s
    """, (file_id, str(play_id)))


def get_episodes(anime_id):
    """Get all episodes for an anime, ordered by episode name."""
    return _execute("""
        SELECT * FROM anime_episodes
        WHERE anime_id = %s
        ORDER BY episode_name
    """, (anime_id,), fetch='all', cursor_factory=RealDictCursor)
