# Soft Support

Кроссплатформенная утилита техподдержки для торговых точек.

## Стек

- **Язык:** Python 3.10+
- **GUI:** customtkinter
- **QR:** qrcode + Pillow
- **Порты:** pyserial (COM), psutil (USB)
- **Сборка:** PyInstaller (один исполняемый файл)

## Структура проекта

```
soft.support/
├── config.json          # Конфигурация торговой точки
├── main.py              # Точка входа
├── requirements.txt     # Зависимости
├── CLAUDE.md
└── src/
    ├── ui/              # GUI компоненты
    ├── utils/           # Утилиты (сеть, порты, QR)
    └── config.py        # Загрузка config.json
```

## Блоки приложения

1. **Клиент** — client_id, telegram_link (QR код), support_phone из config.json
2. **Порты** — USB и COM порты (статус подключения)
3. **Сети** — локальный IP, NetBird IP, Radmin IP

## Платформы

- macOS
- Ubuntu (Linux)
- Windows 10/11

## Правила

- Весь код и комментарии на английском, UI на русском
- Системные команды оборачивать в platform-aware хелперы
- Тестировать кроссплатформенность через проверку `platform.system()`
- config.json лежит рядом с исполняемым файлом
- Язык общения с пользователем: русский
