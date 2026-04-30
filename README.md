# Anime Monitor Bot

Telegram-бот для мониторинга выхода новых серий аниме на сайте [Vost](https://v13.vost.pw).

## Возможности

- **Автоматическая проверка** — бот проверяет сайт каждые 30 минут и уведомляет о новых сериях
- **Поиск аниме** — `/add [название]` ищет аниме на Vost и добавляет в список мониторинга
- **Управление списком** — `/list` показывает текущие серии и даты выхода
- **Расписание** — `/schedule` показывает расписание выхода серий на неделю

## Команды

| Команда | Описание |
|---------|----------|
| `/start` | Начать работу |
| `/list` | Показать список мониторинга |
| `/schedule` | Расписание на неделю |
| `/add [название]` | Добавить аниме |
| `/remove` | Удалить из списка |
| `/help` | Справка |

## Установка

### Требования

- Python 3.10+
- PostgreSQL
- Telegram Bot Token

### Настройка

1. Скопируйте `.env.example` в `.env` и заполните данные:
   - `TOKEN` — токен Telegram-бота
   - `VOST_URL` — URL сайта Vost
   - `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASS` — параметры PostgreSQL

2. Создайте базу данных:
```sql
CREATE DATABASE anime_bot_db;
CREATE USER anime_bot WITH ENCRYPTED PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE anime_bot_db TO anime_bot;
```

3. Запустите бота:
```bash
python3 bot.py
```

Или через systemd (уже настроен в `anime_monitor.service`):
```bash
sudo systemctl enable anime_monitor
sudo systemctl start anime_monitor
```

## Структура проекта

- `bot.py` — Telegram-бот, обработка команд
- `parser.py` — парсер сайта Vost
- `checker.py` — проверка новых серий (для cron)
- `database.py` — работа с PostgreSQL

## Лицензия

MIT