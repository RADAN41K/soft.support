import json
import os
import platform
import sys
import threading
import customtkinter as ctk
from PIL import Image, ImageTk

from src.config import get_base_path, load_config
from src.utils.qr import generate_qr
from src.utils.ports import get_serial_ports, get_usb_devices
from src.utils.network import get_local_ip, get_netbird_ip, get_radmin_ip
from src.utils.logging import log, log_device

EDIT_PASSWORD = "258456"
REFRESH_INTERVAL_MS = 3000


class SoftSupportApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Soft Support — LimanSoft")
        self.minsize(340, 200)
        self._set_icon()
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color="#FFFFFF")
        self.attributes("-topmost", True)

        # Brand colors
        self.ORANGE = "#FF6600"
        self.DARK_ORANGE = "#E55C00"
        self.WHITE = "#FFFFFF"
        self.TEXT_DARK = "#333333"
        self.GREEN = "#15803D"
        self.RED = "#B91C1C"

        self.config_data = {}
        self._qr_image = None
        self._ports_expanded = True
        self._net_expanded = True
        self._tray_icon = None
        self._tray_thread = None

        # Previous values for change detection
        self._prev = {
            "com": "", "usb": "",
            "local_ip": "", "netbird": "", "radmin": "",
            "vpn_status": "",
        }

        self._build_ui()
        self._load_data()
        self._setup_tray()
        self._start_auto_refresh()
        self.after(100, self._fit_height)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        log("Форму запущено, додаток готовий до роботи")

    # --- Icon ---
    def _set_icon(self):
        if getattr(sys, "frozen", False):
            base = sys._MEIPASS
        else:
            base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        icon_png = os.path.join(base, "assets", "icon.png")
        if os.path.exists(icon_png):
            img = Image.open(icon_png)
            self._icon = ImageTk.PhotoImage(img)
            self.iconphoto(True, self._icon)
            self._icon_path = icon_png

    # --- System tray ---
    def _setup_tray(self):
        try:
            import pystray
            icon_path = getattr(self, "_icon_path", None)
            if icon_path and os.path.exists(icon_path):
                tray_image = Image.open(icon_path).resize((64, 64))
            else:
                tray_image = Image.new("RGB", (64, 64), "#FF6600")

            menu = pystray.Menu(
                pystray.MenuItem("Показати", self._tray_show, default=True),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Відкрити логи", self._tray_open_logs),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Закрити", self._tray_quit),
            )
            self._tray_icon = pystray.Icon(
                "SoftSupport", tray_image,
                "LimanSoft Технічна підтримка", menu
            )
            self._tray_thread = threading.Thread(
                target=self._tray_icon.run, daemon=True
            )
            self._tray_thread.start()
            log("Іконку трею запущено")
        except Exception as e:
            log(f"Трей недоступний: {e}", "WARN")

    def _tray_show(self, *_args):
        self.after(0, self._show_window)

    def _tray_open_logs(self, *_args):
        log_dir = os.path.join(get_base_path(), "logs")
        os.makedirs(log_dir, exist_ok=True)
        system = platform.system()
        if system == "Darwin":
            os.system(f'open "{log_dir}"')
        elif system == "Windows":
            os.system(f'explorer "{log_dir}"')
        else:
            os.system(f'xdg-open "{log_dir}"')
        log("Відкрито папку логів")

    def _tray_quit(self, *_args):
        log("Програма закрита користувачем")
        log_device(f"[ПК] Програма зупинена користувачем "
                   f"{os.environ.get('USERNAME', os.environ.get('USER', '?'))}")
        if self._tray_icon:
            self._tray_icon.stop()
        self.after(0, self.destroy)

    def _show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _on_close(self):
        self.withdraw()
        log("Вікно приховано в трей")

    # --- UI ---
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        for i in range(8):
            self.grid_rowconfigure(i, weight=0)

        row = 0

        # --- Block 1: Client / Branding ---
        self.client_frame = ctk.CTkFrame(self, fg_color=self.ORANGE, corner_radius=10)
        self.client_frame.grid(row=row, column=0, padx=10, pady=(10, 5), sticky="ew")
        self.client_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.client_frame, text="Технiчна пiдтримка LimanSoft",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=self.WHITE).grid(
            row=0, column=0, padx=10, pady=(12, 2))

        ctk.CTkLabel(self.client_frame, text="Скануйте QR-код LimanSoft Help 24/7",
                     font=ctk.CTkFont(size=11),
                     text_color=self.WHITE).grid(
            row=1, column=0, padx=10, pady=(0, 5))

        # QR + info centered
        self.info_frame = ctk.CTkFrame(self.client_frame, fg_color="transparent")
        self.info_frame.grid(row=2, column=0, padx=10, pady=(0, 5), sticky="ew")
        self.info_frame.grid_columnconfigure(0, weight=1)
        self.info_frame.grid_columnconfigure(1, weight=0)
        self.info_frame.grid_columnconfigure(2, weight=1)

        center = ctk.CTkFrame(self.info_frame, fg_color="transparent")
        center.grid(row=0, column=1)

        self.lbl_qr = ctk.CTkLabel(center, text="",
                                    fg_color=self.WHITE, corner_radius=8)
        self.lbl_qr.grid(row=0, column=0, pady=(5, 8))

        self.lbl_client_id = ctk.CTkLabel(center, text="—",
                                           font=ctk.CTkFont(size=14, weight="bold"),
                                           text_color=self.WHITE)
        self.lbl_client_id.grid(row=1, column=0, pady=(0, 2))

        self.lbl_phone = ctk.CTkLabel(center, text="—",
                                       font=ctk.CTkFont(size=13),
                                       text_color=self.WHITE)
        self.lbl_phone.grid(row=2, column=0, pady=(0, 2))

        self.lbl_station = ctk.CTkLabel(center, text=f"Станцiя: {platform.node()}",
                                         font=ctk.CTkFont(size=11),
                                         text_color=self.WHITE)
        self.lbl_station.grid(row=3, column=0, pady=(0, 5))

        # Edit button
        self.btn_edit = ctk.CTkButton(
            self.client_frame, text="Редагувати", width=90, height=26,
            fg_color=self.DARK_ORANGE, hover_color="#CC5500",
            font=ctk.CTkFont(size=11),
            command=self._open_config_editor)
        self.btn_edit.grid(row=3, column=0, pady=(0, 10))

        row += 1

        # --- Block 2: Ports (collapsible) ---
        self.ports_header = ctk.CTkFrame(self, fg_color=self.WHITE, border_width=1,
                                          border_color="#E0E0E0", corner_radius=10)
        self.ports_header.grid(row=row, column=0, padx=10, pady=(5, 0), sticky="ew")
        self.ports_header.grid_columnconfigure(0, weight=1)

        self.btn_toggle_ports = ctk.CTkButton(
            self.ports_header, text="\u25BC  USB / COM порти", width=200,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="transparent", hover_color="#F0F0F0",
            text_color=self.TEXT_DARK, anchor="w",
            command=self._toggle_ports)
        self.btn_toggle_ports.grid(row=0, column=0, padx=5, pady=6, sticky="w")

        row += 1

        self.ports_content = ctk.CTkFrame(self, fg_color=self.WHITE, border_width=1,
                                           border_color="#E0E0E0", corner_radius=0)
        self.ports_content.grid(row=row, column=0, padx=10, pady=(0, 0), sticky="ew")
        self.ports_content.grid_columnconfigure(0, weight=1)
        self._ports_row = row

        self.ports_text = ctk.CTkTextbox(self.ports_content, height=100)
        self.ports_text.grid(row=0, column=0, padx=10, pady=(5, 8), sticky="ew")

        row += 1

        # --- Block 3: Network (collapsible) ---
        self.net_header = ctk.CTkFrame(self, fg_color=self.WHITE, border_width=1,
                                        border_color="#E0E0E0", corner_radius=10)
        self.net_header.grid(row=row, column=0, padx=10, pady=(5, 0), sticky="ew")
        self.net_header.grid_columnconfigure(0, weight=1)

        self.btn_toggle_net = ctk.CTkButton(
            self.net_header, text="\u25BC  Мережа", width=200,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="transparent", hover_color="#F0F0F0",
            text_color=self.TEXT_DARK, anchor="w",
            command=self._toggle_net)
        self.btn_toggle_net.grid(row=0, column=0, padx=5, pady=6, sticky="w")

        row += 1

        self.net_content = ctk.CTkFrame(self, fg_color=self.WHITE, border_width=1,
                                         border_color="#E0E0E0", corner_radius=0)
        self.net_content.grid_columnconfigure(1, weight=1)
        self._net_row = row

        ctk.CTkLabel(self.net_content, text="Локальний IP:",
                     text_color=self.TEXT_DARK).grid(
            row=0, column=0, padx=10, pady=2, sticky="w")
        self.lbl_local_ip = ctk.CTkLabel(self.net_content, text="...",
                                          text_color=self.TEXT_DARK)
        self.lbl_local_ip.grid(row=0, column=1, padx=10, pady=2, sticky="w")

        ctk.CTkLabel(self.net_content, text="NetBird IP:",
                     text_color=self.TEXT_DARK).grid(
            row=1, column=0, padx=10, pady=2, sticky="w")
        self.lbl_netbird = ctk.CTkLabel(self.net_content, text="...",
                                         text_color=self.TEXT_DARK)
        self.lbl_netbird.grid(row=1, column=1, padx=10, pady=2, sticky="w")

        ctk.CTkLabel(self.net_content, text="Radmin IP:",
                     text_color=self.TEXT_DARK).grid(
            row=2, column=0, padx=10, pady=(2, 8), sticky="w")
        self.lbl_radmin = ctk.CTkLabel(self.net_content, text="...",
                                        text_color=self.TEXT_DARK)
        self.lbl_radmin.grid(row=2, column=1, padx=10, pady=(2, 8), sticky="w")

        self.net_content.grid(row=self._net_row, column=0, padx=10, pady=(0, 0), sticky="ew")

        row += 1

        # --- VPN Status bar ---
        self.vpn_bar = ctk.CTkFrame(self, fg_color=self.GREEN, corner_radius=8, height=32)
        self.vpn_bar.grid(row=row, column=0, padx=10, pady=(5, 0), sticky="ew")
        self.vpn_bar.grid_columnconfigure(0, weight=1)

        self.lbl_vpn_status = ctk.CTkLabel(
            self.vpn_bar, text="VPN: перевiрка...",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.WHITE)
        self.lbl_vpn_status.grid(row=0, column=0, pady=5)

        row += 1

        # Bottom spacer
        spacer = ctk.CTkFrame(self, fg_color="transparent", height=10)
        spacer.grid(row=row, column=0, sticky="ew")

    # --- Auto refresh ---
    def _start_auto_refresh(self):
        self._do_refresh()

    def _do_refresh(self):
        threading.Thread(target=self._bg_scan, daemon=True).start()
        self.after(REFRESH_INTERVAL_MS, self._do_refresh)

    def _bg_scan(self):
        # Ports
        serial_ports = get_serial_ports()
        usb_devices = get_usb_devices()

        com_str = ", ".join(p["device"] for p in serial_ports) if serial_ports else "Немає"
        usb_str = ", ".join(usb_devices) if usb_devices else "Немає"

        if com_str != self._prev["com"]:
            log_device(f"[COM] Порти змінено: '{self._prev['com']}' -> '{com_str}'")
            self._prev["com"] = com_str
        if usb_str != self._prev["usb"]:
            log_device(f"[USB] Порти змінено: '{self._prev['usb']}' -> '{usb_str}'")
            self._prev["usb"] = usb_str

        # Network
        local_ip = get_local_ip()
        netbird_ip = get_netbird_ip()
        radmin_ip = get_radmin_ip()

        if local_ip != self._prev["local_ip"]:
            log_device(f"[МЕРЕЖА] Локальний IP змінено: '{self._prev['local_ip']}' -> '{local_ip}'")
            self._prev["local_ip"] = local_ip
        if netbird_ip != self._prev["netbird"]:
            log_device(f"[VPN] NetBird: '{self._prev['netbird']}' -> '{netbird_ip}'")
            self._prev["netbird"] = netbird_ip
        if radmin_ip != self._prev["radmin"]:
            log_device(f"[VPN] Radmin: '{self._prev['radmin']}' -> '{radmin_ip}'")
            self._prev["radmin"] = radmin_ip

        vpn_on = (netbird_ip != "Н/Д" and netbird_ip != "—"
                  and not netbird_ip.startswith("Помилка"))
        vpn_status = "on" if vpn_on else "off"
        if vpn_status != self._prev["vpn_status"]:
            if vpn_status == "on":
                log_device(f"[VPN] NetBird ПІДКЛЮЧЕНИЙ | IP: {netbird_ip}")
            else:
                log_device("[VPN] NetBird ВІДКЛЮЧЕНИЙ")
            self._prev["vpn_status"] = vpn_status

        self.after(0, lambda: self._update_ui(
            serial_ports, usb_devices,
            local_ip, netbird_ip, radmin_ip, vpn_on
        ))

    def _update_ui(self, serial_ports, usb_devices,
                   local_ip, netbird_ip, radmin_ip, vpn_on):
        # Ports
        self.ports_text.configure(state="normal")
        self.ports_text.delete("1.0", "end")

        if serial_ports:
            self.ports_text.insert("end", "── COM / Serial ──\n")
            for p in serial_ports:
                self.ports_text.insert("end", f"  {p['device']}  {p['description']}\n")
        else:
            self.ports_text.insert("end", "── COM / Serial ──\n  Немає пристроїв\n")

        self.ports_text.insert("end", "\n")

        if usb_devices:
            self.ports_text.insert("end", "── USB ──\n")
            for d in usb_devices:
                self.ports_text.insert("end", f"  {d}\n")
        else:
            self.ports_text.insert("end", "── USB ──\n  Немає пристроїв\n")

        self.ports_text.configure(state="disabled")

        # Network
        self.lbl_local_ip.configure(text=local_ip)
        self.lbl_netbird.configure(text=netbird_ip)
        self.lbl_radmin.configure(text=radmin_ip)

        # VPN bar
        if vpn_on:
            self.vpn_bar.configure(fg_color=self.GREEN)
            self.lbl_vpn_status.configure(
                text=f"VPN активний  |  NetBird пiдключений")
        else:
            self.vpn_bar.configure(fg_color=self.RED)
            self.lbl_vpn_status.configure(text="NetBird вiдключений")

    # --- Fit height ---
    def _fit_height(self):
        self.update_idletasks()
        req_w = max(self.winfo_reqwidth(), self.winfo_width(), 380)
        req_h = self.winfo_reqheight()
        self.geometry(f"{req_w}x{req_h}")

    # --- Toggle sections ---
    def _toggle_ports(self):
        if self._ports_expanded:
            self.ports_content.grid_forget()
            self.btn_toggle_ports.configure(text="\u25B6  USB / COM порти")
            self._ports_expanded = False
        else:
            self.ports_content.grid(row=self._ports_row, column=0, padx=10,
                                    pady=(0, 0), sticky="ew")
            self.btn_toggle_ports.configure(text="\u25BC  USB / COM порти")
            self._ports_expanded = True
        self._fit_height()

    def _toggle_net(self):
        if self._net_expanded:
            self.net_content.grid_forget()
            self.btn_toggle_net.configure(text="\u25B6  Мережа")
            self._net_expanded = False
        else:
            self.net_content.grid(row=self._net_row, column=0, padx=10,
                                  pady=(0, 0), sticky="ew")
            self.btn_toggle_net.configure(text="\u25BC  Мережа")
            self._net_expanded = True
        self._fit_height()

    # --- Load config ---
    def _load_data(self):
        try:
            self.config_data = load_config()
        except Exception as e:
            self.config_data = {}
            self.lbl_client_id.configure(text=f"Помилка: {e}")
            log(f"Помилка завантаження конфігу: {e}", "ERROR")
            return

        self.lbl_client_id.configure(
            text=self.config_data.get("client_id", "—"))
        self.lbl_phone.configure(
            text=self.config_data.get("support_phone", "—"))
        log(f"Клієнт: {self.config_data.get('client_id')} | "
            f"Телефон: {self.config_data.get('support_phone')}")

        tg_link = self.config_data.get("telegram_link", "")
        if tg_link:
            qr_img = generate_qr(tg_link, size=140)
            self._qr_image = ctk.CTkImage(
                light_image=qr_img, dark_image=qr_img, size=(140, 140))
            self.lbl_qr.configure(image=self._qr_image, text="")

    # --- Config editor ---
    def _open_config_editor(self):
        pwd_dialog = ctk.CTkInputDialog(
            text="Введiть пароль:", title="Доступ")
        pwd = pwd_dialog.get_input()
        if pwd != EDIT_PASSWORD:
            if pwd is not None:
                log("Невдала спроба входу до налаштувань", "WARN")
            return

        log("Відкрито редактор налаштувань")
        editor = ctk.CTkToplevel(self)
        editor.title("Налаштування клiєнта — LimanSoft")
        editor.geometry("400x300")
        editor.attributes("-topmost", True)
        editor.grab_set()

        editor.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(editor, text="Клiєнт (назва):",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=20, pady=(20, 2), sticky="w")
        entry_client = ctk.CTkEntry(editor, width=360)
        entry_client.insert(0, self.config_data.get("client_id", ""))
        entry_client.grid(row=1, column=0, padx=20, pady=(0, 10))

        ctk.CTkLabel(editor, text="QR посилання (Telegram):",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=2, column=0, padx=20, pady=(0, 2), sticky="w")
        entry_link = ctk.CTkEntry(editor, width=360)
        entry_link.insert(0, self.config_data.get("telegram_link", ""))
        entry_link.grid(row=3, column=0, padx=20, pady=(0, 10))

        ctk.CTkLabel(editor, text="Телефон пiдтримки:",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=4, column=0, padx=20, pady=(0, 2), sticky="w")
        entry_phone = ctk.CTkEntry(editor, width=360)
        entry_phone.insert(0, self.config_data.get("support_phone", ""))
        entry_phone.grid(row=5, column=0, padx=20, pady=(0, 20))

        def save():
            new_data = {
                "client_id": entry_client.get().strip(),
                "telegram_link": entry_link.get().strip(),
                "support_phone": entry_phone.get().strip(),
            }
            if not all(new_data.values()):
                return

            config_path = os.path.join(get_base_path(), "config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(new_data, f, ensure_ascii=False, indent=4)

            self.config_data = new_data
            self.lbl_client_id.configure(text=new_data["client_id"])
            self.lbl_phone.configure(text=new_data["support_phone"])
            log(f"Конфіг оновлено: Клієнт={new_data['client_id']}, "
                f"Телефон={new_data['support_phone']}")

            # Regenerate QR
            if new_data["telegram_link"]:
                qr_img = generate_qr(new_data["telegram_link"], size=140)
                self._qr_image = ctk.CTkImage(
                    light_image=qr_img, dark_image=qr_img, size=(140, 140))
                self.lbl_qr.configure(image=self._qr_image, text="")

            editor.destroy()

        ctk.CTkButton(editor, text="Зберегти", width=160,
                      fg_color=self.ORANGE, hover_color=self.DARK_ORANGE,
                      command=save).grid(row=6, column=0, pady=(0, 20))
