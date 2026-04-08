# Збiрка Soft Support

## Пiдготовка (всi платформи)

```bash
git clone <repo-url> soft.support
cd soft.support
python -m venv venv
source venv/bin/activate        # macOS / Linux / Git Bash
pip install -r requirements.txt
pip install pyinstaller
```

Запуск для розробки:

```bash
source venv/bin/activate && python main.py
```

---

## macOS

### Вимоги

```bash
# create-dmg - для DMG з вiкном та стрiлкою "перетягни в Applications"
# Без нього DMG буде простий (тiльки .app без ярлика на Applications)
brew install create-dmg
```

### Збiрка

```bash
python build.py
```

Результат:

```
dist/
├── SoftSupport.app    - додаток
└── SoftSupport.dmg    - образ для розповсюдження
```

### Встановлення на точцi

1. Скопiювати `SoftSupport.dmg` + `config.json` на Mac
2. Вiдкрити DMG, перетягнути `SoftSupport.app` в `Applications`
3. Покласти `config.json` поряд з `.app`
4. Запустити з Launchpad або Finder

Ярлик на робочому столi: перетягнути `SoftSupport.app` з Applications на Desktop з затиснутим Cmd+Opt.

---

## Linux (Ubuntu 22.04+)

### Збiрка через Docker (з macOS або будь-якої ОС)

```bash
./build-linux.sh
```

Потрiбен Docker Desktop. Скрипт автоматично збирає контейнер Ubuntu 22.04, компiлює бiнарник та створює .deb пакет.

### Збiрка нативно (на Ubuntu)

```bash
python build.py
./build-deb.sh
```

Результат:

```
dist/
├── SoftSupport                            - бiнарник
└── limansoft-support_X.X.X_amd64.deb      - установник
```

### Встановлення на точцi

```bash
sudo apt install ./limansoft-support_X.X.X_amd64.deb
```

Установник:
- Копiює програму в `~/.local/softsupport/`
- Створює ярлик на робочому столi
- Додає автозапуск
- Встановлює розширення для iконки в треї
- Автооновлення працює без sudo

Пiсля першої установки потрiбен перелогiн (вийти/увiйти) для iконки в треї.

Видалення: `sudo dpkg -r limansoft-support`

---

## Windows

### Збiрка Win 10/11

**PowerShell / CMD:**
```powershell
py -3.14 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
python build.py
```

**Git Bash:**
```bash
py -3.14 -m venv venv
source venv/Scripts/activate
pip install -r requirements.txt
pip install pyinstaller
python build.py
```

### Збiрка Win 7

Потрiбен Python 3.8 (остання версiя з пiдтримкою Windows 7): [python.org/downloads/release/python-3813](https://www.python.org/downloads/release/python-3813/)

**PowerShell / CMD:**
```powershell
py -3.8 -m venv venv38
venv38\Scripts\activate
pip install -r requirements-win7.txt
pip install pyinstaller
python build.py
```

**Git Bash:**
```bash
py -3.8 -m venv venv38
source venv38/Scripts/activate
pip install -r requirements-win7.txt
pip install pyinstaller
python build.py
```

Вiдмiнностi Win 7: без `truststore`, обмежено верхнi версiї залежностей (Pillow<11, watchdog<5, qrcode<8).

`py -3.8` / `py -3.14` - вбудований Windows Python Launcher, автоматично знаходить потрiбну версiю.

### Результат

```
dist\
└── SoftSupport.exe
```

### Створення установника (Inno Setup)

1. Завантажити [Inno Setup](https://jrsoftware.org/isdl.php) (безкоштовно)
2. Вiдкрити `installer.iss` в Inno Setup Compiler
3. Натиснути **Build -> Compile** (або Ctrl+F9)
4. Готовий файл: `dist\SoftSupport_Setup.exe`

> Якщо пiсля оновлення iконка на робочому столi не змiнилась - скинути кеш:
> `ie4uinit.exe -ClearIconCache`

Що робить установник:
- Встановлює в `C:\Program Files\SoftSupport\`
- Копiює `config.json` поряд з `.exe`
- Створює ярлик на робочому столi (галочка при встановленнi)
- Додає в меню "Пуск"
- Деiнсталятор через "Програми та компоненти"

### Встановлення на точцi

1. Скопiювати `SoftSupport_Setup.exe` на ПК
2. Запустити - Далi - Встановити
3. Вiдредагувати `config.json` в папцi встановлення пiд конкретну точку

---

## Завантаження на сервер оновлень

Сервер: https://limansoft.com - Система - Оновлення

Для кожної платформи потрiбно завантажити установник (для технiкiв) та бiнарник (для автооновлення).

| Платформа  | download_url (установник)                | binary_url (автооновлення)                        |
|------------|------------------------------------------|---------------------------------------------------|
| Windows 7  | `dist/SoftSupport_Setup.exe`             | `dist/SoftSupport.exe`                            |
| Windows 10 | `dist/SoftSupport_Setup.exe`             | `dist/SoftSupport.exe`                            |
| Windows 11 | `dist/SoftSupport_Setup.exe`             | `dist/SoftSupport.exe`                            |
| macOS      | `dist/SoftSupport.dmg`                   | `dist/SoftSupport.app/Contents/MacOS/SoftSupport` |
| Linux      | `dist/limansoft-support_X.X.X_amd64.deb` | `dist/SoftSupport` (з Docker)                     |

- **download_url** - файл для технiкiв, встановлення на нових точках
- **binary_url** - файл для автооновлення на iснуючих точках
- Windows: автооновлення працює через установник, але бiнарник теж варто додати на всяк випадок
- macOS/Linux: автооновлення замiнює бiнарник напряму

---

## config.json

Кожна торгова точка має свiй `config.json`:

```json
{
    "client_id": "Назва точки",
    "telegram_link": "https://t.me/your_chat",
    "support_phone": "+380 XX XXX XX XX"
}
```

Файл повинен лежати поряд з програмою:
- macOS: поряд з `SoftSupport.app`
- Windows: поряд з `SoftSupport.exe` (в папцi встановлення)
- Linux: поряд з бiнарником `SoftSupport`
