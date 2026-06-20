# 📰 Новостной бот

Telegram-бот который собирает новости с 22 источников, суммаризирует их через AI и присылает дайджест каждые 7 минут.

---

## Что умеет

- 7 категорий: 🌍 Мир · 🇺🇦 Украина · 🇪🇺 Европа · 🇺🇸 США · 💻 Технологии · 🚗 Авто · 💰 Финансы
- Дайджест каждые **7 минут** — Claude суммаризирует и объединяет похожие новости
- **Breaking news** каждые 2 минуты — срочное летит сразу без ожидания
- Мультипользователь — мама/папа пишут `/start`, тебе приходит кнопка одобрить/отклонить
- Дедупликация — одна новость с 5 сайтов = 1 пункт в дайджесте

---

## Что нужно перед запуском

### 1. Telegram Bot Token
1. Открой Telegram, найди `@BotFather`
2. Напиши `/newbot`
3. Придумай имя и username (например `@my_news_bot`)
4. Скопируй токен — выглядит так: `7123456789:AAF...`

### 2. Твой Chat ID
1. Найди в Telegram бота `@userinfobot`
2. Напиши ему `/start`
3. Он пришлёт твой ID — числа типа `123456789`

### 3. Anthropic API Key
1. Зайди на `console.anthropic.com`
2. Войди или зарегистрируйся
3. Settings → API Keys → Create Key
4. Скопируй — выглядит так: `sk-ant-api03-...`
5. Пополни баланс — $5 хватит на месяцы работы

---

## Хостинг — Hetzner CX22 (€3.79/мес)

### Регистрация
1. Зайди на `hetzner.com` → Cloud → Register
2. Верифицируй карту (€1 холд, вернётся)

### Создание сервера
1. Hetzner Console → **New Server**
2. Локация: **Nuremberg** или **Helsinki**
3. OS: **Ubuntu 24.04**
4. Тип: **CX22** (2 vCPU, 4GB RAM)
5. SSH Key — добавь свой публичный ключ (или используй пароль)
6. Нажми **Create & Buy**
7. Запомни IP сервера

### Подключение к серверу
```bash
ssh root@ВАШ_IP
```

---

## Установка на сервере

```bash
# Обновить систему
apt update && apt upgrade -y

# Установить Python и pip
apt install python3 python3-pip python3-venv -y

# Создать папку
mkdir -p /opt/news_bot && cd /opt/news_bot

# Создать виртуальное окружение
python3 -m venv venv
source venv/bin/activate
```

---

## Загрузка файлов

**Со своего компьютера** (в новом терминале):
```bash
scp news_bot.zip root@ВАШ_IP:/opt/news_bot/
```

**На сервере:**
```bash
cd /opt/news_bot
apt install unzip -y
unzip news_bot.zip
mv news_bot/* .
rm -rf news_bot news_bot.zip
```

---

## Настройка .env

```bash
cp .env.example .env
nano .env
```

Заполни три строки:
```
TELEGRAM_TOKEN=сюда_токен_от_BotFather
ANTHROPIC_API_KEY=сюда_ключ_от_Anthropic
ADMIN_ID=сюда_твой_chat_id
```

Сохранить в nano: `Ctrl+O` → Enter → `Ctrl+X`

---

## Установка зависимостей

```bash
source venv/bin/activate
pip install -r requirements.txt
```

---

## Тестовый запуск

```bash
python bot.py
```

Если всё ок — в Telegram придёт сообщение "🤖 Новостной бот запущен!".  
Остановить: `Ctrl+C`

---

## Автозапуск (systemd)

Чтобы бот работал всегда — даже после перезагрузки сервера:

```bash
nano /etc/systemd/system/news_bot.service
```

Вставить:
```ini
[Unit]
Description=News Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/news_bot
ExecStart=/opt/news_bot/venv/bin/python bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Сохранить: `Ctrl+O` → Enter → `Ctrl+X`

```bash
# Включить и запустить
systemctl daemon-reload
systemctl enable news_bot
systemctl start news_bot

# Проверить статус
systemctl status news_bot
```

---

## Команды бота

| Команда | Кто может | Что делает |
|---|---|---|
| `/start` | Все | Запросить доступ |
| `/digest` | Все юзеры | Получить дайджест прямо сейчас |
| `/breaking` | Все юзеры | Проверить срочные новости |
| `/help` | Все юзеры | Список команд |
| `/users` | Только ты | Список всех пользователей |
| `/removeuser ID` | Только ты | Удалить пользователя |
| `/pause 2h` | Только ты | Пауза (можно 30m, 2h, 1440m) |
| `/resume` | Только ты | Возобновить |
| `/status` | Только ты | Статус бота и число юзеров |

---

## Как добавить маму/папу

1. Они открывают бота в Telegram и пишут `/start`
2. Им приходит: *"запрос отправлен администратору"*
3. Тебе приходит карточка с их именем и двумя кнопками
4. Нажимаешь **✅ Одобрить** — они начинают получать дайджест

---

## Полезные команды на сервере

```bash
# Посмотреть логи в реальном времени
journalctl -u news_bot -f

# Перезапустить бота
systemctl restart news_bot

# Остановить бота
systemctl stop news_bot

# Посмотреть последние 50 строк логов
journalctl -u news_bot -n 50
```

---

## Структура файлов

```
news_bot/
├── bot.py          — главный файл, команды, планировщик
├── config.py       — источники RSS, настройки интервалов
├── db.py           — база данных (пользователи, статьи)
├── aggregator.py   — скачивает и фильтрует RSS
├── summarizer.py   — суммаризация через Claude API
├── requirements.txt
├── .env            — твои ключи (не публиковать!)
└── news_bot.db     — SQLite база (создаётся автоматически)
```

---

## Добавить новый источник новостей

Открой `config.py`, найди нужную категорию и добавь строку:

```python
"💻 ТЕХНОЛОГИИ": [
    ("TechCrunch",  "https://techcrunch.com/feed/"),
    ("Новый сайт",  "https://example.com/rss"),   # ← добавил сюда
],
```

Перезапусти бота: `systemctl restart news_bot`

---

## Частые проблемы

**Бот не запускается**
→ Проверь `.env` — все три переменные заполнены?  
→ `python bot.py` — смотри текст ошибки

**Нет новостей в дайджесте**
→ Нормально если несколько минут пусто — новости копятся  
→ Попробуй `/digest` вручную

**Один из источников не грузится**
→ Смотри логи: `journalctl -u news_bot -n 100`  
→ Этот источник просто пропускается, остальные работают

**Бот упал и не поднимается**
→ `systemctl status news_bot` — там причина  
→ `systemctl restart news_bot`
