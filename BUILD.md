# Збірка Soft Support

## Вимоги (всі платформи)

- Python 3.10+
- Python 3.8 (для збiрки Windows 7)
- pip

## Підготовка

```bash
# Клонувати репозиторій
git clone <repo-url> soft.support
cd soft.support

# Створити віртуальне середовище
# macOS / Linux:
python -m venv venv
source venv/bin/activate

# Windows (див. нижче про збiрку для Win 7 та Win 10/11 на однiй машинi):
py -3.14 -m venv venv
venv\Scripts\activate

# Встановити залежності
pip install -r requirements.txt
pip install pyinstaller
```

## Швидкi команди

```bash
# Запуск програми (розробка/тестування)
source venv/bin/activate && python main.py

# Збiрка бiнарника
source venv/bin/activate && python build.py
```

---

## macOS

### Збірка

```bash
python build.py
```

### Результат

```
dist/
├── SoftSupport.app    ← додаток
├── SoftSupport.dmg    ← образ для розповсюдження
└── config.json        ← конфігурація (покласти вручну)
```

### Встановлення на торговій точці

1. Скопіювати `SoftSupport.dmg` + `config.json` на Mac
2. Відкрити DMG, перетягнути `SoftSupport.app` в `Applications`
3. Покласти `config.json` поряд з `.app` (або в `/Applications/`)
4. Запустити з Launchpad або Finder

### Ярлик на робочому столі

Перетягнути `SoftSupport.app` з Applications на Desktop з затиснутим ⌘+⌥ (створить alias).

---

## Windows 7

### Вимоги

- Python 3.8 (остання версія з пiдтримкою Windows 7)
- Windows 7 SP1

### Збірка

```powershell
# Встановити Python 3.8 (python.org/downloads/release/python-3813/)
py -3.8 -m venv venv38
venv38\Scripts\activate
pip install -r requirements-win7.txt
pip install pyinstaller
python build.py
```

### Вiдмiнностi вiд Windows 10/11

- Без `truststore` - SSL працює через `certifi` (fallback)
- Обмежено верхнi версiї залежностей (Pillow<11, watchdog<5, qrcode<8)

### Результат

```
dist\
└── SoftSupport.exe    ← для Windows 7
```

Установник та встановлення - аналогiчно Windows 10/11 (див. нижче).

---

## Збiрка Win 7 та Win 10/11 на однiй машинi

На Windows 10 можна збирати обидвi версiї. Встановiть Python 3.8 та 3.10+, далi використовуйте окремi вiртуальнi оточення:

```powershell
# Збiрка для Win 7
py -3.8 -m venv venv38
venv38\Scripts\activate
pip install -r requirements-win7.txt
pip install pyinstaller
python build.py
deactivate

# Збiрка для Win 10/11
py -3.14 -m venv venv314
venv314\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
python build.py
deactivate
```

`py -3.8` / `py -3.14` - вбудований Windows Python Launcher, автоматично знаходить потрiбну версiю. Оточення iзольованi, конфлiктiв не буде.

---

## Windows 10 / 11

### Збірка

```powershell
py -3.14 -m venv venv314
venv314\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller
python build.py
```

### Результат

```
dist\
└── SoftSupport.exe    ← один виконуваний файл
```

### Створення установника (Inno Setup)

1. Завантажити [Inno Setup](https://jrsoftware.org/isdl.php) (безкоштовно)
2. Відкрити `installer.iss` в Inno Setup Compiler
3. Натиснути **Build → Compile** (або Ctrl+F9)
4. Готовий файл: `dist\SoftSupport_Setup.exe`

### Що робить установник

- Встановлює в `C:\Program Files\SoftSupport\`
- Копіює `config.json` поряд з `.exe`
- Створює ярлик на робочому столі (галочка при встановленні)
- Додає в меню "Пуск"
- Деінсталятор через "Програми та компоненти"

### Встановлення на торговій точці

1. Скопіювати `SoftSupport_Setup.exe` на ПК
2. Запустити → Далі → Встановити
3. Відредагувати `config.json` в папці встановлення під конкретну точку

---

## Ubuntu / Linux

### Збірка

```bash
python build.py
```

### Результат

```
dist/
└── SoftSupport        ← бінарний файл
~/Desktop/
└── SoftSupport.desktop  ← ярлик (створюється автоматично)
```

### Встановлення на торговій точці

1. Скопіювати `dist/SoftSupport` + `config.json` на ПК
2. Зробити виконуваним: `chmod +x SoftSupport`
3. Покласти в `/opt/softsupport/` або `/home/user/`:
   ```bash
   sudo mkdir -p /opt/softsupport
   sudo cp SoftSupport config.json /opt/softsupport/
   sudo chmod +x /opt/softsupport/SoftSupport
   ```
4. Створити ярлик на робочому столі:
   ```bash
   cat > ~/Desktop/SoftSupport.desktop << 'EOF'
   [Desktop Entry]
   Version=1.0
   Type=Application
   Name=Soft Support
   Comment=LimanSoft Tech Support
   Exec=/opt/softsupport/SoftSupport
   Icon=/opt/softsupport/icon.png
   Terminal=false
   Categories=Utility;
   EOF
   chmod +x ~/Desktop/SoftSupport.desktop
   ```

---

## config.json

Кожна торгова точка має свій `config.json`:

```json
{
    "client_id": "Назва точки",
    "telegram_link": "https://t.me/your_chat",
    "support_phone": "+380 XX XXX XX XX"
}
```

**Важливо:** файл повинен лежати **поряд** з програмою:
- macOS: поряд з `SoftSupport.app`
- Windows: поряд з `SoftSupport.exe` (в папці встановлення)
- Linux: поряд з бінарником `SoftSupport`
