# Промпт для развёртывания через Devin (GLM-5.2)

Скопируйте этот текст целиком и отправьте Devin в новом чате.
Devin развернёт систему на вашем сервере и соберёт десктоп-приложение.

---

## ПРОМПТ ДЛЯ DEVIN

Ты — DevOps-инженер. Разверни Telegram lead-generation систему HunterZetronix на моём сервере и собери десктоп-приложение для Windows.

### Шаг 1. Клонирование проекта

```bash
git clone https://github.com/kudinov13/HunterZetronix.git
cd HunterZetronix
```

### Шаг 2. Подготовка сервера

Сервер: Linux (Ubuntu 22.04+ или Debian 12+), Python 3.11+.

```bash
# Установить системные пакеты
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git

# Виртуальное окружение
python3 -m venv .venv
source .venv/bin/activate

# Зависимости
pip install -r requirements.txt
```

### Шаг 3. Настройка .env

Скопируй `.env.example` в `.env` и заполни значениями, которые я тебе дам.

**Мне нужно от пользователя:**
1. **Telegram API credentials** — получить на https://my.telegram.org:
   - `TG_API_ID` (число)
   - `TG_API_HASH` (строка)
   - `TG_PHONE` (номер в формате +79991234567)

2. **Notification bot** — создать бота через @BotFather в Telegram:
   - `NOTIF_BOT_TOKEN` (токен бота)
   - `OWNER_TG_ID` (мой Telegram ID — узнать через @userinfobot)

3. **GigaChat API** — зарегистрироваться на https://developers.sber.ru/portal/products/gigachat:
   - `GIGACHAT_API_KEY` (base64-строка client_id:client_secret)
   - `GIGACHAT_SCOPE` = `GIGACHAT_API_PERS`

4. **API_TOKEN** — придумай случайный токен для защиты HTTP API (например, 32 случайных символа)

5. **Прокси** (если сервер в РФ и Telegram заблокирован):
   - MTProto или SOCKS5 прокси — заполнить `TG_MTPROTO_*` или `TG_PROXY_*`
   - Для Bot API — `TG_BOT_PROXY` (socks5://... или http://...)

Спроси у меня все эти значения перед запуском. НЕ придумывай их сам.

### Шаг 4. Инициализация Telegram-сессии

```bash
source .venv/bin/activate
python -c "
from user_client import UserClient
import asyncio
async def init():
    client = UserClient()
    await client.start_interactive()
asyncio.run(init())
"
```

Telegram пришлёт код подтверждения на номер телефона. Введи его когда попросит.
Если потребуется 2FA — введи пароль.

После успешной авторизации появится файл `work_account.session` — НЕ удаляй его и НЕ коммить в git.

### Шаг 5. Запуск сервера

```bash
source .venv/bin/activate
python main.py
```

Проверь что в логах:
- `✅ Система запущена! Ожидание лидов...`
- `HTTP API запущен на порту 8080`
- `Запуск бота уведомлений...`

Если есть ошибки — исправь их. Частые проблемы:
- `GIGACHAT_API_KEY` неверный → проверь ключ
- Telegram не подключается → настрой прокси
- Порт 8080 занят → поменяй порт или останови конфликтующий процесс

### Шаг 6. Настройка systemd-сервиса

Создай файл `/etc/systemd/system/lead-hunter.service`:

```ini
[Unit]
Description=Lead Hunter — Telegram Lead Generation
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/HunterZetronix
ExecStart=/opt/HunterZetronix/.venv/bin/python /opt/HunterZetronix/main.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

**ВАЖНО:** Замени `/opt/HunterZetronix` на реальный путь к проекту.

```bash
sudo systemctl daemon-reload
sudo systemctl enable lead-hunter
sudo systemctl start lead-hunter
sudo systemctl status lead-hunter  # должно быть active (running)
```

### Шаг 7. Сборка десктоп-приложения (Windows)

На Windows-машине:

```bash
git clone https://github.com/kudinov13/HunterZetronix.git
cd HunterZetronix
pip install -r requirements.txt
python build_exe.py
```

Рядом с `dist/LeadHunter.exe` создай файл `.env`:
```
SERVER_URL=http://ВАШ_СЕРВЕР_IP:8080
API_TOKEN=ТОТ_ЖЕ_ТОКЕН_ЧТО_НА_СЕРВЕРЕ
```

Запусти `dist/LeadHunter.exe`. Программа подключится к серверу.

### Шаг 8. Проверка

1. Открой Telegram, найди своего бота уведомлений, отправь `/start`
2. В GUI нажми «СИНХРОН» — загрузятся чаты из Telegram
3. Выбери чат, включи «ЧИТАТЬ», задай правила, нажми «СОХРАНИТЬ»
4. Нажми «ТЕСТ» — AI сгенерирует тестовое сообщение
5. Нажми «ЗАПУСК» — парсинг начнётся

### Шаг 9. Настройка чатов

Для каждого чата в GUI:
- **ЧИТАТЬ** — включить поиск лидов
- **РАССЫЛКА** — включить AI-рассылку
- **ПРАВИЛА ЧАТА** — вставить текст правил (или отметить «ПРАВИЛ НЕТ»)
- **ВРЕМЯ РАССЫЛКИ** — формат: `10:00, 19:30`
- **ТЕМАТИКА ЧАТА** — например «крипта P2P», «рестораны», «недвижимость»
- **ЯЗЫК РАССЫЛКИ** — выбрать язык чата (ru, en, ar, pt, id, kz, uz, az)
- **ПОЛ РАЗРАБОТЧИКА** — male или female (влияет на тексты AI)

### Важные замечания

1. **НЕ коммить `.env` в git** — там секреты. Файл уже в `.gitignore`
2. **НЕ удаляй `*.session` файлы** — это авторизация Telegram, без неё придётся заново входить
3. **GigaChat лимиты** — бесплатный тариф имеет ограничения. Если упрётесь — переключи на `GigaChat-Pro` или используй запасной провайдер (Groq)
4. **Анти-бан** — не включай рассылку сразу во всех чатах. Начни с 2-3, постепенно увеличивай
5. **Прокси** — если сервер в РФ, Telegram заблокирован. Нужен MTProto или SOCKS5 прокси
6. **Переводчик** — MyMemory API бесплатный (5000 слов/день). При превышении — GigaChat fallback
7. **База данных** — SQLite, файл `data/bot.db`. Для бэкапа просто скопируй файл

### Если что-то не работает

- Логи сервера: `journalctl -u lead-hunter -f`
- Логи GUI: файл `gui.log` рядом с exe
- Проверь `.env` — все ли значения заполнены
- Проверь интернет и прокси
- Проверь что GigaChat API ключ валидный: `python -c "from ai_engine import _get_gigachat_token; import asyncio; print(asyncio.run(_get_gigachat_token()))"`

### Команды бота уведомлений

После запуска отправь боту `/start` — откроется меню:
- 🔥 Лиды — список найденных лидов
- 💬 Диалоги — активные AI-диалоги с клиентами
- 🔍 Поиск чатов — поиск новых чатов по ключевым словам
- ❄️ Холодный обход — поиск косвенных лидов
- 📈 Статистика — метрики за день/неделю
- ⚙️ Настройки — параметры системы
- ⏸ Остановить парсинг / ▶️ Запустить парсинг

---

## КОНЕЦ ПРОМПТА

Скопируй всё выше (начиная с "## ПРОМПТ ДЛЯ DEVIN") и отправь Devin.
Devin попросит тебя ввести значения для .env — подготовь их заранее.
