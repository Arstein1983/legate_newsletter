# Деплой Newsletter Bot на сервер

Пошаговая инструкция для VPS (Aeza, Ubuntu 24.04).

**Сервер:** `77.110.106.118`  
**Папка на сервере:** `/opt/newsletter_bot`  
**SSH:** подключаться **с VPN** (без VPN часто `Connection refused`)

---

## Содержание

1. [Подключение к серверу](#1-подключение-к-серверу)
2. [Подготовка сервера](#2-подготовка-сервера)
3. [Загрузка проекта](#3-загрузка-проекта)
4. [Настройка .env](#4-настройка-env)
5. [Запуск MySQL](#5-запуск-mysql)
6. [Python и зависимости](#6-python-и-зависимости)
7. [Авторизация Telethon](#7-авторизация-telethon)
8. [Проверочный запуск](#8-проверочный-запуск)
9. [Автозапуск (systemd)](#9-автозапуск-systemd)
10. [Первый вход в боте](#10-первый-вход-в-боте)
11. [Обновление и перезапуск](#11-обновление-и-перезапуск)
12. [Частые ошибки](#12-частые-ошибки)
13. [Чеклист](#13-чеклист)

---

## 1. Подключение к серверу

### Windows (PowerShell, VPN включён)

Если после переустановки ОС была ошибка про host key:

```powershell
ssh-keygen -R 77.110.106.118
```

Подключение:

```powershell
ssh root@77.110.106.118
```

| Параметр | Значение |
|----------|----------|
| Логин | `root` |
| Пароль | из панели Aeza |

Если SSH не работает — откройте **Console / VNC** в браузере (панель Aeza).

---

## 2. Подготовка серера

На сервере выполните:

```bash
apt update && apt upgrade -y
apt install -y git python3 python3-venv python3-pip docker.io docker-compose
systemctl enable --now docker
mkdir -p /opt/newsletter_bot
```

> **Примечание:** если пакет `docker-compose-plugin` не находится — используйте `docker-compose` (с дефисом), как выше.

### Диалоги при apt upgrade

| Окно | Что выбрать |
|------|-------------|
| Keyboard layout | **English (US)** → Ok |
| openssh-server / sshd_config | **keep the local version currently installed** → Ok |

---

## 3. Загрузка проекта

### С ПК (PowerShell, VPN)

```powershell
cd d:\projects\newsletter_bot
scp -r app main.py requirements.txt docker-compose.yml .env.example root@77.110.106.118:/opt/newsletter_bot/
```

Если `.env` уже заполнен локально:

```powershell
scp .env root@77.110.106.118:/opt/newsletter_bot/
```

---

## 4. Настройка .env

На сервере (если `.env` ещё не скопировали):

```bash
cd /opt/newsletter_bot
cp .env.example .env
nano .env
```

Пример содержимого:

```env
BOT_TOKEN=...
ADMIN_IDS=123456789,987654321
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=newsletter
MYSQL_PASSWORD=надёжный_пароль
MYSQL_DATABASE=newsletter
TELEGRAM_API_ID=...
TELEGRAM_API_HASH=...
SEND_DELAY_SECONDS=4
```

| Переменная | Описание |
|------------|----------|
| `BOT_TOKEN` | Токен от [@BotFather](https://t.me/BotFather) |
| `ADMIN_IDS` | Telegram user id через запятую |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | С [my.telegram.org/apps](https://my.telegram.org/apps) |

Пароль MySQL должен совпадать в `.env` и в `docker-compose.yml` (если меняете).

---

## 5. Запуск MySQL

```bash
cd /opt/newsletter_bot
docker-compose up -d
docker ps
```

Должен быть контейнер `newsletter_mysql`.

Проверка логов:

```bash
docker logs newsletter_mysql
```

---

## 6. Python и зависимости

```bash
cd /opt/newsletter_bot
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## 7. Авторизация Telethon

Рассылка идёт **с вашего аккаунта Telegram**, не от бота. Нужен файл `sessions/admin.session`.

### Вариант A — авторизация на сервере (рекомендуется)

**Код вводите в SSH-терминал**, не в чат бота:

```bash
cd /opt/newsletter_bot
source venv/bin/activate
python -c "
import asyncio
from telethon import TelegramClient
from app.config import get_settings, SESSIONS_DIR

async def main():
    s = get_settings()
    SESSIONS_DIR.mkdir(exist_ok=True)
    client = TelegramClient(str(SESSIONS_DIR / 'admin'), s.telegram_api_id, s.telegram_api_hash)
    await client.start(phone=lambda: input('Phone (+7965...): '))
    me = await client.get_me()
    print('OK:', me.first_name, me.id)
    await client.disconnect()

asyncio.run(main())
"
```

После строки `OK: ...` сессия сохранена.

### Вариант B — скопировать с ПК

Только если бот **на ПК остановлен**. Копировать **только** `admin.session`:

```powershell
scp d:\projects\newsletter_bot\sessions\admin.session root@77.110.106.118:/opt/newsletter_bot/sessions/
```

`admin.session-journal` **не копировать**.

На сервере:

```bash
mkdir -p /opt/newsletter_bot/sessions
chmod 600 /opt/newsletter_bot/sessions/admin.session
```

---

## 8. Проверочный запуск

```bash
cd /opt/newsletter_bot
source venv/bin/activate
python main.py
```

В Telegram напишите боту `/start` или нажмите **▶️ Старт**.

Если всё работает — остановите: **Ctrl+C**.

> **Важно:** не запускайте бота одновременно на ПК и на сервере.

---

## 9. Автозапуск (systemd)

Создайте сервис:

```bash
nano /etc/systemd/system/newsletter-bot.service
```

Содержимое:

```ini
[Unit]
Description=Newsletter Telegram Bot
After=network.target docker.service
Requires=docker.service

[Service]
Type=simple
WorkingDirectory=/opt/newsletter_bot
ExecStart=/opt/newsletter_bot/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Запуск и автозагрузка:

```bash
systemctl daemon-reload
systemctl enable newsletter-bot
systemctl start newsletter-bot
systemctl status newsletter-bot
```

Логи:

```bash
journalctl -u newsletter-bot -f
```

---

## 10. Первый вход в боте

1. `/start` или кнопка **▶️ Старт**
2. **Настройки** — проверить авторизацию аккаунта для рассылки
3. **Группы** — создать группу, добавить `@username` или телефоны
4. **Шаблоны** — сохранить сообщение для рассылки
5. **Рассылка** — группа → шаблон → запуск

---

## 11. Обновление и перезапуск

### Если бот работает через systemd (основной режим)

После изменений в коде или `.env`:

```bash
systemctl restart newsletter-bot
```

| Команда | Действие |
|---------|----------|
| `systemctl restart newsletter-bot` | Перезапуск |
| `systemctl stop newsletter-bot` | Остановить |
| `systemctl start newsletter-bot` | Запустить |
| `systemctl status newsletter-bot` | Статус |
| `journalctl -u newsletter-bot -f` | Логи в реальном времени |

### Что менялось — что делать

| Изменили | Действие |
|----------|----------|
| Код (`app/`, `main.py`) | Залить файлы → `systemctl restart newsletter-bot` |
| `.env` | Отредактировать → `systemctl restart newsletter-bot` |
| `requirements.txt` | `pip install -r requirements.txt` → restart |
| `docker-compose.yml` / MySQL | `docker-compose up -d` → restart бота |
| `sessions/admin.session` | Restart бота |

### Залить изменения с ПК

**На ПК (VPN):**

```powershell
cd d:\projects\newsletter_bot
scp -r app main.py root@77.110.106.118:/opt/newsletter_bot/
scp .env root@77.110.106.118:/opt/newsletter_bot/
```

**На сервере:**

```bash
systemctl restart newsletter-bot
journalctl -u newsletter-bot -f
```

### Если бот запущен вручную (без systemd)

1. **Ctrl+C** в терминале с ботом
2. Снова:

```bash
cd /opt/newsletter_bot
source venv/bin/activate
python main.py
```

---

## 12. Частые ошибки

| Ошибка | Решение |
|--------|---------|
| `Connection refused` (SSH) | Подключаться **с VPN** |
| `Host key verification failed` | `ssh-keygen -R 77.110.106.118` |
| `kex_exchange_identification: Connection closed` | Консоль Aeza → `systemctl restart ssh` |
| `Unable to locate package docker-compose-plugin` | `apt install docker.io docker-compose` |
| `Unauthorized` (бот) | Проверить `BOT_TOKEN` в `.env` |
| Нет доступа к боту | Проверить `ADMIN_IDS` |
| MySQL не стартует | `docker logs newsletter_mysql` |
| Бот не отвечает | `journalctl -u newsletter-bot -f` |
| Два экземпляра бота | Остановить бота на ПК, оставить только сервер |

---

## 13. Чеклист

| # | Шаг | Готово |
|---|-----|--------|
| 1 | SSH с VPN работает | ☐ |
| 2 | `apt update`, Docker, Python установлены | ☐ |
| 3 | Проект в `/opt/newsletter_bot` | ☐ |
| 4 | `.env` заполнен | ☐ |
| 5 | `docker-compose up -d` | ☐ |
| 6 | `pip install -r requirements.txt` | ☐ |
| 7 | `sessions/admin.session` есть | ☐ |
| 8 | `systemctl enable newsletter-bot` | ☐ |
| 9 | Бот отвечает в Telegram | ☐ |
| 10 | Бот на ПК остановлен | ☐ |

---

## Быстрая шпаргалка

```bash
# Подключение (на ПК с VPN)
ssh root@77.110.106.118

# На сервере
cd /opt/newsletter_bot
docker-compose up -d
systemctl restart newsletter-bot
journalctl -u newsletter-bot -f
```

---

*Файл создан для проекта `newsletter_bot`. Обновляйте IP и пути при смене сервера.*
