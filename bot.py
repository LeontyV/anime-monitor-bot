import asyncio
import hashlib
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv('TOKEN')
BOT_USERNAME = os.getenv('BOT_USERNAME')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import get_monitored_anime, add_anime, remove_anime, get_anime_by_url, mark_notified, init_db, add_episodes, get_episodes
from parser import fetchAnimeList, get_full_episode_info, get_episode_list, get_video_url

ALLOWED_USER_ID = int(os.getenv('ALLOWED_USER_ID', '68650276'))
SCHEDULE_ITEMS_LIMIT = int(os.getenv('SCHEDULE_ITEMS_LIMIT', '5'))

VOST_BASE_URL = "https://v13.vost.pw"
DAY_NAMES = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']


def url_hash(url):
    """Short hash for callback data."""
    return hashlib.md5(url.encode()).hexdigest()[:12]


async def auth_check(update: Update) -> bool:
    return update.effective_user.id == ALLOWED_USER_ID


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    await update.message.reply_text(
        "🎬 *Anime Monitor Bot*\n\n"
        "Я слежу за выходом серий аниме на Vost и оповещаю тебя о новых сериях.\n\n"
        "Доступные команды:\n"
        "/list — показать список мониторинга\n"
        "/schedule — показать расписание на сегодня\n"
        "/add — добавить аниме в список\n"
        "/videos — смотреть видео (серии аниме)\n"
        "/remove — удалить из списка\n"
        "/help — помощь",
        parse_mode=ParseMode.MARKDOWN
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    await update.message.reply_text(
        "📖 *Справка*\n\n"
        "/list — показать список мониторинга\n"
        "/schedule — показать расписание на сегодня\n"
        "/add — добавить аниме (интерактивное меню)\n"
        "/remove — удалить из списка\n"
        "/videos — смотреть видео (серии аниме)\n"
        "/parse — обновить список с Vost\n\n"
        "После добавления аниме в список, бот будет проверять сайт каждые 30 минут "
        "и присылать оповещения о новых сериях.",
        parse_mode=ParseMode.MARKDOWN
    )


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    anime_list = get_monitored_anime()
    if not anime_list:
        await update.message.reply_text("📭 Список мониторинга пуст.\nИспользуй /add для добавления аниме.")
        return
    text = "📋 *Список мониторинга:*\n\n"
    for anime in anime_list:
        ep_info = f"{anime['current_episode']}"
        if anime['total_episodes']:
            ep_info += f" / {anime['total_episodes']}"
        text += f"• [{anime['title_ru']}]({VOST_BASE_URL}{anime['vost_url']})\n"
        text += f"  Серия: {ep_info}\n"
        if anime['next_episode_date']:
            text += f"  Следующая: {anime['next_episode_date']}\n\n"
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)


async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    try:
        anime_list = fetchAnimeList()
        schedule_by_day = {}
        for anime in anime_list:
            if anime.get('type') == 'schedule':
                day = anime.get('day', 'Unknown')
                if day not in schedule_by_day:
                    schedule_by_day[day] = []
                schedule_by_day[day].append(anime)
        if not schedule_by_day:
            await update.message.reply_text("📭 Расписание пусто.")
            return
        today_num = datetime.now().weekday()
        ordered_days = DAY_NAMES[today_num:] + DAY_NAMES[:today_num]
        text = "📅 *Расписание на неделю:*\n\n"
        for day_name in ordered_days:
            if day_name not in schedule_by_day:
                continue
            day_items = schedule_by_day[day_name]
            fixed_items = [a for a in day_items if a.get('time') != 'day']
            if not fixed_items:
                continue
            marker = "📌" if day_name == DAY_NAMES[today_num] else "  "
            text += f"{marker} *{day_name}*\n"
            for anime in sorted(fixed_items, key=lambda x: x.get('time') or 'zz'):
                has_time = ' (' in anime['title'] and ')' in anime['title']
                time_str = f" ({anime['time']})" if anime.get('time') and not has_time else ""
                text += f"  • [{anime['title']}]({VOST_BASE_URL}{anime['url']}){time_str}\n"
            text += "\n"
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка парсинга: {e}")


def _build_days_keyboard():
    """Build inline keyboard with days of the week (3 columns)."""
    buttons = []
    row = []
    for i, day in enumerate(DAY_NAMES):
        row.append(InlineKeyboardButton(day, callback_data=f"d{i}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        while len(row) < 3:
            row.append(InlineKeyboardButton(" ", callback_data="noop"))
        buttons.append(row)
    buttons.append([InlineKeyboardButton("❌ Выйти", callback_data="exit")])
    return InlineKeyboardMarkup(buttons)


def _build_anime_keyboard(anime_list, added_urls):
    """Build inline keyboard with anime titles for a selected day.
    added_urls: set of URLs already in monitoring list.
    """
    buttons = []
    for anime in anime_list:
        title = anime['title'][:50] + "..." if len(anime['title']) > 50 else anime['title']
        h = url_hash(anime['url'])
        if anime['url'] in added_urls:
            # Already added: show checkmark, callback becomes 'added_' (no-op)
            buttons.append([InlineKeyboardButton(f"✅ {title}", callback_data=f"added_{h}")])
        else:
            buttons.append([InlineKeyboardButton(f"➕ {title}", callback_data=f"a{h}")])
    buttons.append([
        InlineKeyboardButton("◀️ К дням", callback_data="back"),
        InlineKeyboardButton("❌ Выйти", callback_data="exit")
    ])
    return InlineKeyboardMarkup(buttons)


async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return

    await update.message.reply_text(
        "📅 *Выбери день недели:*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_build_days_keyboard()
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await auth_check(update):
        await query.answer("⛔ Доступ запрещён.", show_alert=True)
        return

    await query.answer()
    data = query.data

    # --- Day selected: show anime for that day ---
    if data.startswith("d"):
        day_idx = int(data[1:])
        day = DAY_NAMES[day_idx]
        try:
            anime_list = fetchAnimeList()
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка загрузки: {e}", parse_mode=ParseMode.MARKDOWN)
            return

        day_anime = [
            a for a in anime_list
            if a.get('day') == day and a.get('type') == 'schedule' and a.get('time') != 'day'
        ]

        if not day_anime:
            await query.answer(f"📭 На {day} ничего не запланировано.", show_alert=True)
            return

        # Reset url_map and store only this day's anime
        context.user_data['url_map'] = {}
        for anime in day_anime:
            h = url_hash(anime['url'])
            context.user_data['url_map'][h] = anime

        # Get URLs already in monitoring list
        monitored = get_monitored_anime()
        added_urls = {a['vost_url'] for a in monitored}

        await query.edit_message_text(
            f"📅 *{day}* — выбери аниме:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_build_anime_keyboard(day_anime, added_urls)
        )
        return

    # --- Already added: no-op with toast ---
    if data.startswith("added_"):
        await query.answer("✅ Уже в списке мониторинга.", show_alert=False)
        return

    # --- Anime selected: add to DB ---
    if data.startswith("a"):
        h = data[1:]
        url_map = context.user_data.get('url_map', {})
        anime = url_map.get(h)

        if not anime:
            await query.answer("❌ Данные устарели. Начни с /add заново.", show_alert=True)
            return

        try:
            info = get_full_episode_info(anime['url'])
        except Exception as e:
            await query.answer(f"❌ Ошибка: {e}", show_alert=True)
            return

        if not info or not info.get('title_ru'):
            await query.answer("❌ Не удалось получить информацию.", show_alert=True)
            return

        title_clean = info['title_ru'].replace('[', '(').replace(']', ')').replace('*', '')
        try:
            add_anime(
                title_clean,
                info['title_en'],
                anime['url'],
                info['current_episode'],
                info['total_episodes'],
                info['next_episode_date'],
                None
            )
        except Exception:
            pass

        # Re-render keyboard with updated added status
        monitored = get_monitored_anime()
        added_urls = {a['vost_url'] for a in monitored}

        # Get day_anime from url_map
        day_anime = list(url_map.values())

        await query.answer("✅ Добавлено!")
        await query.edit_message_text(
            f"📅 *Выбери ещё аниме:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_build_anime_keyboard(day_anime, added_urls)
        )
        return

    # --- Back to days ---
    if data == "back":
        await query.edit_message_text(
            "📅 *Выбери день недели:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_build_days_keyboard()
        )
        return

    # --- Exit: close menu cleanly ---
    if data == "exit":
        try:
            await query.delete_message()
        except Exception:
            try:
                await query.edit_message_text("👋 *Меню закрыто.*", parse_mode=ParseMode.MARKDOWN)
            except Exception:
                pass
        return


async def videos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show monitored anime list grouped by days for video browsing."""
    if not await auth_check(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    anime_list = get_monitored_anime()
    if not anime_list:
        await update.message.reply_text("📭 Список мониторинга пуст.\nИспользуй /add для добавления аниме.")
        return
    await update.message.reply_text(
        "🎬 *Выбери аниме:*",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=_build_videos_anime_keyboard(anime_list)
    )


def _build_videos_anime_keyboard(anime_list):
    """Build inline keyboard with monitored anime titles."""
    buttons = []
    for anime in anime_list:
        title = anime['title_ru'][:50] + "..." if len(anime['title_ru']) > 50 else anime['title_ru']
        h = url_hash(anime['vost_url'])
        buttons.append([InlineKeyboardButton(f"🎬 {title}", callback_data=f"v{h}")])
    buttons.append([InlineKeyboardButton("❌ Выйти", callback_data="exit")])
    return InlineKeyboardMarkup(buttons)


def _build_episodes_keyboard(anime, episodes):
    """Build inline keyboard with episode buttons for selected anime."""
    buttons = []
    for ep in episodes:
        ep_label = ep['episode_name'][:20]
        buttons.append([InlineKeyboardButton(f"▶ {ep_label}", callback_data=f"ep{ep['play_id']}")])
    buttons.append([
        InlineKeyboardButton("◀️ К списку", callback_data="videos_back"),
        InlineKeyboardButton("❌ Выйти", callback_data="exit")
    ])
    return InlineKeyboardMarkup(buttons)


async def videos_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle video menu callbacks."""
    query = update.callback_query
    if not await auth_check(update):
        await query.answer("⛔ Доступ запрещён.", show_alert=True)
        return

    await query.answer()
    data = query.data

    # --- Back to anime list ---
    if data == "videos_back":
        anime_list = get_monitored_anime()
        if not anime_list:
            await query.edit_message_text("📭 Список мониторинга пуст.", parse_mode=ParseMode.MARKDOWN)
            return
        await query.edit_message_text(
            "🎬 *Выбери аниме:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_build_videos_anime_keyboard(anime_list)
        )
        return

    # --- Anime selected: sync episodes from Vost, then show from DB ---
    if data.startswith("v"):
        h = data[1:]
        anime_list = get_monitored_anime()
        anime = next((a for a in anime_list if url_hash(a['vost_url']) == h), None)
        if not anime:
            await query.answer("❌ Аниме не найдено.", show_alert=True)
            return

        # Sync new episodes from Vost to DB
        try:
            fresh_episodes = get_episode_list(anime['vost_url'])
            if fresh_episodes:
                add_episodes(anime['id'], fresh_episodes)
        except Exception as e:
            pass  # Silently fail — DB may already have episodes

        # Load from DB
        episodes = get_episodes(anime['id'])
        if not episodes:
            await query.answer("📭 Серии не найдены.", show_alert=True)
            return

        # Store in context for fast lookup
        context.user_data['current_video_anime'] = anime
        context.user_data['current_episodes'] = {str(ep['play_id']): dict(ep) for ep in episodes}

        await query.edit_message_text(
            f"🎬 *{anime['title_ru']}*\nВыбери серию:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=_build_episodes_keyboard(anime, episodes)
        )
        return

    # --- Episode selected: fetch 720p URL and send ---
    if data.startswith("ep"):
        play_id = data[2:]
        episodes = context.user_data.get('current_episodes', {})
        ep = episodes.get(play_id)
        if not ep:
            await query.answer("❌ Данные устарели. Начни с /videos заново.", show_alert=True)
            return

        await query.answer("▶ Открываю...", show_alert=False)

        video_url = get_video_url(play_id)
        if not video_url:
            await query.answer("❌ Не удалось получить ссылку на видео.", show_alert=True)
            return

        ep_name = ep.get('episode_name', 'Видео')
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"▶ *{ep_name}*\n\n[Смотреть видео]({video_url})",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=False
        )

        return

    # --- Exit ---
    if data == "exit":
        try:
            await query.delete_message()
        except Exception:
            try:
                await query.edit_message_text("👋 *Меню закрыто.*", parse_mode=ParseMode.MARKDOWN)
            except Exception:
                pass
        return


async def remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    anime_list = get_monitored_anime()
    if not anime_list:
        await update.message.reply_text("📭 Список мониторинга пуст.")
        return
    keyboard = []
    for anime in anime_list:
        keyboard.append([InlineKeyboardButton(f"🗑 {anime['title_ru'][:40]}", callback_data=f"rem_{anime['id']}")])
    keyboard.append([InlineKeyboardButton("❌ Выйти", callback_data="rem_exit")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🗑 *Выбери аниме для удаления:*", parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)


async def remove_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await auth_check(update):
        await query.answer("⛔ Доступ запрещён.", show_alert=True)
        return
    await query.answer()
    data = query.data

    if data == "rem_exit":
        try:
            await query.delete_message()
        except Exception:
            try:
                await query.edit_message_text("👋 *Меню закрыто.*", parse_mode=ParseMode.MARKDOWN)
            except Exception:
                pass
        return

    if data.startswith('rem_'):
        anime_id = int(data[4:])
        anime = next((a for a in get_monitored_anime() if a['id'] == anime_id), None)
        if anime:
            remove_anime(anime_id)
            await query.answer("🗑 Удалено!")
        else:
            await query.answer("❌ Не найдено.", show_alert=True)
            return

        # Re-render keyboard without deleted item
        anime_list = get_monitored_anime()
        if not anime_list:
            await query.edit_message_text("📭 Список мониторинга пуст.", parse_mode=ParseMode.MARKDOWN)
            return

        keyboard = []
        for a in anime_list:
            keyboard.append([InlineKeyboardButton(f"🗑 {a['title_ru'][:40]}", callback_data=f"rem_{a['id']}")])
        keyboard.append([InlineKeyboardButton("❌ Выйти", callback_data="rem_exit")])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🗑 *Выбери аниме для удаления:*",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=reply_markup
        )


async def parse_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    await update.message.reply_text("🔄 Парсинг расписания с Vost...")
    try:
        anime_list = fetchAnimeList()
        schedule_by_time = {}
        updates = []
        for anime in anime_list:
            if anime.get('type') == 'schedule':
                time = anime.get('time', 'day')
                if time not in schedule_by_time:
                    schedule_by_time[time] = []
                schedule_by_time[time].append(anime['title'])
            else:
                updates.append(anime['title'])
        text = f"📋 *Найдено {len(anime_list)} аниме на Vost*\n\n"
        for time in sorted(schedule_by_time.keys()):
            text += f"🕐 *{time}:*\n"
            for title in schedule_by_time[time][:SCHEDULE_ITEMS_LIMIT]:
                text += f"• {title}\n"
            if len(schedule_by_time[time]) > SCHEDULE_ITEMS_LIMIT:
                text += f"  ...и ещё {len(schedule_by_time[time]) - SCHEDULE_ITEMS_LIMIT}\n"
            text += "\n"
        if updates:
            text += "📆 *Последние обновления:*\n"
            for title in updates[:10]:
                text += f"• {title}\n"
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка парсинга: {e}")


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")


def main():
    init_db()
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("schedule", schedule_command))
    app.add_handler(CommandHandler("add", add_command))
    app.add_handler(CommandHandler("videos", videos_command))
    app.add_handler(CommandHandler("remove", remove_command))
    app.add_handler(CommandHandler("parse", parse_command))
    app.add_handler(CallbackQueryHandler(button_callback, pattern=r"^(d\d|a[0-9a-f]+|added_[0-9a-f]+|back|exit|noop)$"))
    app.add_handler(CallbackQueryHandler(remove_callback, pattern=r"^rem_"))
    app.add_handler(CallbackQueryHandler(videos_callback, pattern=r"^(v[0-9a-f]+|ep[0-9]+|videos_back|exit)$"))
    app.add_error_handler(error_handler)
    logger.info("Anime Monitor Bot started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()
