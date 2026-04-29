import asyncio
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

# Import database functions
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import get_monitored_anime, add_anime, remove_anime, get_anime_by_url, mark_notified, init_db

# Import parser
from parser import fetchAnimeList, get_full_episode_info

# Known user ID (Leonty)
ALLOWED_USER_ID = 68650276

async def auth_check(update: Update) -> bool:
    """Check if user is authorized."""
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
        "/schedule — показать расписание сегодня\n"
        "/add — добавить аниме в список\n"
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
        "/add — добавить аниме (введите название или ссылку)\n"
        "/remove — удалить из списка\n"
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
        text += f"• {anime['title_ru']}\n"
        text += f"  Серия: {ep_info}\n"
        if anime['next_episode_date']:
            text += f"  Следующая: {anime['next_episode_date']}\n"
        text += f"  [Инфо]({anime['vost_url']})\n\n"
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)

async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    
    try:
        anime_list = fetchAnimeList()
        
        # Group by day
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
        
        # Determine current day of week
        today_num = datetime.now().weekday()  # 0=Mon, 6=Sun
        day_names = ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье']
        today_name = day_names[today_num]
        
        # Show all days (starting from today)
        ordered_days = day_names[today_num:] + day_names[:today_num]
        
        text = "📅 *Расписание на неделю:*\n\n"
        
        for day_name in ordered_days:
            if day_name not in schedule_by_day:
                continue
            day_items = schedule_by_day[day_name]
            
            # Skip items with time='day' (непостоянные релизы)
            fixed_items = [a for a in day_items if a.get('time') != 'day']
            if not fixed_items:
                continue
            
            marker = "📌" if day_name == today_name else "  "
            text += f"{marker} *{day_name}*\n"
            for anime in sorted(fixed_items, key=lambda x: x.get('time') or 'zz'):
                time_str = f" ({anime['time']})" if anime.get('time') else ""
                text += f"  • {anime['title']}{time_str}\n"
            text += "\n"
        
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True)
    
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка парсинга: {e}")

async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "➕ *Добавить аниме*\n\n"
            "Использование:\n"
            "/add [название или ссылка]\n\n"
            "Например:\n"
            "/add Начало после конца\n"
            "/add https://v13.vost.pw/tip/tv/3820-saikyou-no-ousama-nidome-no-jinsei-wa-nani-wo-suru-season-2.html",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    query = ' '.join(context.args)
    
    # Check if it's a URL
    if query.startswith('http'):
        url = query
        await update.message.reply_text("🔍 Ищу информацию по ссылке...")
        info = get_full_episode_info(url)
        if info:
            add_anime(
                info['title_ru'] or query,
                info['title_en'],
                url,
                info['current_episode'],
                info['total_episodes'],
                info['next_episode_date'],
                None
            )
            await update.message.reply_text(
                f"✅ *Добавлено в список мониторинга:*\n"
                f"{info['title_ru']}\n"
                f"Текущая серия: {info['current_episode']}",
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text("❌ Не удалось получить информацию с страницы.")
        return
    
    # Search in the anime list
    await update.message.reply_text("🔍 Ищу на Vost...")
    try:
        anime_list = fetchAnimeList()
        query_lower = query.lower()
        matches = [a for a in anime_list if query_lower in a['title'].lower()]
        
        if not matches:
            await update.message.reply_text("😕 Ничего не найдено. Попробуй точнее название или ссылку.")
            return
        
        if len(matches) == 1:
            anime = matches[0]
            info = get_full_episode_info(anime['url'])
            if info:
                add_anime(
                    info['title_ru'],
                    info['title_en'],
                    anime['url'],
                    info['current_episode'],
                    info['total_episodes'],
                    info['next_episode_date'],
                    None
                )
                await update.message.reply_text(
                    f"✅ *Добавлено в список мониторинга:*\n"
                    f"{info['title_ru']}\n"
                    f"Текущая серия: {info['current_episode']}",
                    parse_mode=ParseMode.MARKDOWN
                )
        else:
            # Show selection
            text = "🔍 *Найдено несколько совпадений:*\n\n"
            keyboard = []
            for i, anime in enumerate(matches[:10]):
                title_short = anime['title'][:50] + "..." if len(anime['title']) > 50 else anime['title']
                text += f"{i+1}. {title_short}\n"
                keyboard.append([InlineKeyboardButton(f"{i+1}. {title_short[:30]}", callback_data=f"add_{anime['url']}")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)
    
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

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
        keyboard.append([InlineKeyboardButton(f"❌ {anime['title_ru'][:40]}", callback_data=f"rem_{anime['id']}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("🗑 *Выбери аниме для удаления:*", parse_mode=ParseMode.MARKDOWN, reply_markup=reply_markup)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    
    if not await auth_check(update):
        await query.answer("⛔ Доступ запрещён.", show_alert=True)
        return
    
    await query.answer()
    
    data = query.data
    
    if data.startswith('add_'):
        url = data[4:]
        info = get_full_episode_info(url)
        if info:
            add_anime(
                info['title_ru'],
                info['title_en'],
                url,
                info['current_episode'],
                info['total_episodes'],
                info['next_episode_date'],
                None
            )
            await query.edit_message_text(
                f"✅ *Добавлено:*\n{info['title_ru']}\nСерия: {info['current_episode']}",
                parse_mode=ParseMode.MARKDOWN
            )
    
    elif data.startswith('rem_'):
        anime_id = int(data[4:])
        anime = next((a for a in get_monitored_anime() if a['id'] == anime_id), None)
        if anime:
            remove_anime(anime_id)
            await query.edit_message_text(f"🗑 *Удалено:*\n{anime['title_ru']}", parse_mode=ParseMode.MARKDOWN)

async def parse_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await auth_check(update):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    
    await update.message.reply_text("🔄 Парсинг расписания с Vost...")
    
    try:
        anime_list = fetchAnimeList()
        
        text = f"📋 *Найдено {len(anime_list)} аниме на Vost*\n\n"
        
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
        
        for time in sorted(schedule_by_time.keys()):
            text += f"🕐 *{time}:*\n"
            for title in schedule_by_time[time][:5]:
                text += f"• {title}\n"
            if len(schedule_by_time[time]) > 5:
                text += f"  ...и ещё {len(schedule_by_time[time]) - 5}\n"
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
    # Initialize database
    init_db()
    
    app = Application.builder().token(TOKEN).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CommandHandler("schedule", schedule_command))
    app.add_handler(CommandHandler("add", add_command))
    app.add_handler(CommandHandler("remove", remove_command))
    app.add_handler(CommandHandler("parse", parse_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_error_handler(error_handler)
    
    logger.info("Anime Monitor Bot started!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
