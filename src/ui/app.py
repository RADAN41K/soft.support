import os
import platform
import sys
import threading
import tkinter
import customtkinter as ctk
from PIL import Image, ImageTk

from src.config import load_or_fetch_config, fetch_from_api, save_config
from src.version import __version__
from src.utils.qr import generate_qr
from src.utils.ports import get_serial_ports, get_usb_devices
from src.utils.network import get_local_ip, get_netbird_ip, get_radmin_ip
from src.utils.logging import log, log_device, get_log_dir
from src.utils.autostart import is_autostart_enabled, set_autostart
from src.utils.updater import check_and_apply_silently

EDIT_PASSWORD = "258456"
REFRESH_INTERVAL_MS = 3000

# Brand colors
ORANGE = "#FF6600"
DARK_ORANGE = "#E55C00"
WHITE = "#FFFFFF"
TEXT_DARK = "#333333"
GREEN = "#15803D"
RED = "#B91C1C"
BORDER_COLOR = "#E0E0E0"

# Values considered inactive/disconnected
INACTIVE_PREFIXES = ("Помилка", "Не ")
INACTIVE_VALUES = ("Н/Д", "—", "Не підключений", "Не подключён",
                   "Не установлен", "Не определён")


def _is_active_ip(ip):
    """Check if IP value represents an active connection."""
    if ip in INACTIVE_VALUES:
        return False
    return not any(ip.startswith(p) for p in INACTIVE_PREFIXES)


class SoftSupportApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title(f"LimanSoft Support — v{__version__}")
        self.minsize(370, 200)
        self.geometry("430x200")
        self._set_icon()
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color=WHITE)
        self.attributes("-topmost", True)

        self.config_data = {}
        self._qr_image = None
        self._tray_icon = None
        self._tray_thread = None

        # Collapsible sections state: {name: (button, content, row, expanded)}
        self._sections = {}
        self._port_count = 0
        self._net_count = 0

        # Previous values for change detection
        self._prev = {}

        self._build_ui()
        self._load_data()
        self._setup_tray()
        self._start_auto_refresh()
        self.resizable(True, False)
        self.after(300, self._fit_height)
        self.after(1000, self._fit_height)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        log(f"Форму запущено v{__version__}, додаток готовий до роботи")

        # Check for updates silently in background
        check_and_apply_silently()

    def run(self):
        """Start the application."""
        self.mainloop()

    # --- Icon ---
    def _set_icon(self):
        if getattr(sys, "frozen", False):
            base = sys._MEIPASS
        else:
            base = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        icon_png = os.path.join(base, "assets", "icon.png")
        icon_ico = os.path.join(base, "assets", "icon.ico")
        # Windows: use .ico for taskbar and title bar icon
        if platform.system() == "Windows" and os.path.exists(icon_ico):
            self.iconbitmap(icon_ico)
        elif os.path.exists(icon_png):
            img = Image.open(icon_png)
            self._icon = ImageTk.PhotoImage(img)
            self.iconphoto(True, self._icon)
        if os.path.exists(icon_png):
            self._icon_path = icon_png

    # --- System tray ---
    def _setup_tray(self):
        try:
            if platform.system() == "Darwin":
                log("macOS: сворачування у Dock замість трею")
                return
            import pystray
            icon_path = getattr(self, "_icon_path", None)
            if icon_path and os.path.exists(icon_path):
                tray_image = Image.open(icon_path).resize((64, 64))
            else:
                tray_image = Image.new("RGB", (64, 64), ORANGE)

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
        self._open_log_folder()

    def _open_log_folder(self):
        log_dir = get_log_dir()
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
        if self._tray_icon:
            self.withdraw()
            log("Вікно приховано в трей")
        elif platform.system() == "Darwin":
            self.iconify()
            log("Вікно згорнуто у Dock")
        else:
            self._tray_quit()

    # --- UI ---
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        for i in range(8):
            self.grid_rowconfigure(i, weight=0)

        row = 0

        # --- Block 1: Client / Branding ---
        self.client_frame = ctk.CTkFrame(self, fg_color=ORANGE, corner_radius=10)
        self.client_frame.grid(row=row, column=0, padx=10, pady=(10, 0), sticky="ew")
        self.client_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.client_frame, text="Технiчна пiдтримка LimanSoft",
                     font=ctk.CTkFont(size=17, weight="bold"),
                     text_color=WHITE).grid(
            row=0, column=0, padx=10, pady=(6, 0))

        self.lbl_help_link = ctk.CTkLabel(
            self.client_frame, text="Скануйте QR-код LimanSoft Help 24/7",
            font=ctk.CTkFont(size=13),
            text_color=WHITE)
        self.lbl_help_link.grid(row=1, column=0, padx=10, pady=(1, 0))

        # QR + client info side by side
        self.info_frame = ctk.CTkFrame(self.client_frame, fg_color="transparent")
        self.info_frame.grid(row=2, column=0, padx=10, pady=(1, 6), sticky="ew")
        self.info_frame.grid_columnconfigure(0, weight=1)
        self.info_frame.grid_columnconfigure(1, weight=0)
        self.info_frame.grid_columnconfigure(2, weight=0)
        self.info_frame.grid_columnconfigure(3, weight=1)

        # Spacer left
        ctk.CTkFrame(self.info_frame, fg_color="transparent", width=1).grid(
            row=0, column=0)

        self.lbl_qr = ctk.CTkLabel(self.info_frame, text="",
                                    fg_color=WHITE, corner_radius=6)
        self.lbl_qr.grid(row=0, column=1, padx=(0, 10), pady=0)

        right = ctk.CTkFrame(self.info_frame, fg_color="transparent")
        right.grid(row=0, column=2)

        self.lbl_pos_id = ctk.CTkLabel(right, text="—",
                                        font=ctk.CTkFont(size=18, weight="bold"),
                                        text_color=WHITE)
        self.lbl_pos_id.grid(row=0, column=0, sticky="w")

        self.lbl_shop_name = ctk.CTkLabel(right, text="—",
                                            font=ctk.CTkFont(size=13),
                                            text_color=WHITE)
        self.lbl_shop_name.grid(row=1, column=0, sticky="w")

        ctk.CTkLabel(right, text="Номер тех.пiдтримки:",
                     font=ctk.CTkFont(size=10),
                     text_color="#FFD5B0").grid(row=2, column=0, sticky="w")

        self.lbl_phone = ctk.CTkLabel(right, text="—",
                                       font=ctk.CTkFont(size=15),
                                       text_color=WHITE)
        self.lbl_phone.grid(row=3, column=0, sticky="w")

        self.btn_edit = ctk.CTkButton(
            right, text="Редагувати", width=80, height=22,
            fg_color=DARK_ORANGE, hover_color="#CC5500",
            font=ctk.CTkFont(size=10),
            command=self._open_config_editor)
        self.btn_edit.grid(row=4, column=0, sticky="w", pady=(4, 0))

        self.btn_logs = ctk.CTkButton(
            right, text="Логи", width=80, height=22,
            fg_color=DARK_ORANGE, hover_color="#CC5500",
            font=ctk.CTkFont(size=10),
            command=self._open_logs_with_password)
        self.btn_logs.grid(row=5, column=0, sticky="w", pady=(2, 0))

        self.btn_hide = ctk.CTkButton(
            right, text="Вихiд", width=80, height=22,
            fg_color=DARK_ORANGE, hover_color="#CC5500",
            font=ctk.CTkFont(size=10),
            command=self._on_close)
        self.btn_hide.grid(row=6, column=0, sticky="w", pady=(2, 0))

        # Spacer right
        ctk.CTkFrame(self.info_frame, fg_color="transparent", width=1).grid(
            row=0, column=3)

        row += 1

        # --- Block 2: Ports (collapsible) ---
        row = self._build_collapsible_section(
            "ports", "USB / COM порти", row)

        self.ports_text = ctk.CTkTextbox(
            self._sections["ports"]["content"], height=100)
        self.ports_text.grid(row=0, column=0, padx=10, pady=(5, 8), sticky="ew")

        # --- Block 3: Network (collapsible) ---
        row = self._build_collapsible_section(
            "net", "Мережа", row)

        net_content = self._sections["net"]["content"]
        net_content.grid_columnconfigure(1, weight=1)

        self.lbl_local_ip = self._build_ip_row(net_content, "Локальний IP:", 0)
        self.lbl_netbird = self._build_ip_row(net_content, "NetBird IP:", 1)
        self.lbl_radmin = self._build_ip_row(net_content, "Radmin IP:", 2, last=True)

        # --- VPN Status bar ---
        self.vpn_bar = ctk.CTkFrame(self, fg_color=GREEN, corner_radius=10, height=32)
        self.vpn_bar.grid(row=row, column=0, padx=10, pady=(10, 10), sticky="ew")
        self.vpn_bar.grid_columnconfigure(0, weight=1)

        self.lbl_vpn_status = ctk.CTkLabel(
            self.vpn_bar, text="VPN: перевiрка...",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=WHITE)
        self.lbl_vpn_status.grid(row=0, column=0, pady=5)

        row += 1

        # Bottom spacer
        ctk.CTkFrame(self, fg_color="transparent", height=10).grid(
            row=row, column=0, sticky="ew")

    def _build_collapsible_section(self, name, label, row):
        """Build a collapsible header + content frame. Returns next row."""
        header = ctk.CTkFrame(self, fg_color=WHITE, border_width=1,
                              border_color=BORDER_COLOR, corner_radius=10)
        header.grid(row=row, column=0, padx=10, pady=(10, 0), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        btn = ctk.CTkButton(
            header, text=f"\u25B6  {label}",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="transparent", hover_color="#F0F0F0",
            text_color=TEXT_DARK, anchor="w",
            command=lambda: self._toggle_section(name))
        btn.grid(row=0, column=0, padx=5, pady=6, sticky="ew")

        row += 1

        content = ctk.CTkFrame(self, fg_color=WHITE, border_width=1,
                               border_color=BORDER_COLOR, corner_radius=10)
        content.grid_columnconfigure(0, weight=1)

        self._sections[name] = {
            "button": btn,
            "content": content,
            "row": row,
            "label": label,
            "expanded": False,
        }

        row += 1
        return row

    def _build_ip_row(self, parent, label_text, row, last=False):
        """Build a network IP row with label, value, and copy button. Returns value label."""
        pady = (2, 8) if last else 2

        ctk.CTkLabel(parent, text=label_text,
                     text_color=TEXT_DARK).grid(
            row=row, column=0, padx=10, pady=pady, sticky="w")

        lbl = ctk.CTkLabel(parent, text="...", text_color=TEXT_DARK)
        lbl.grid(row=row, column=1, padx=10, pady=pady, sticky="w")

        ctk.CTkButton(
            parent, text="\U0001f4cb", width=28, height=22,
            fg_color="#E0E0E0", hover_color="#D0D0D0", text_color=TEXT_DARK,
            font=ctk.CTkFont(size=12),
            command=lambda: self._copy_ip(lbl)
        ).grid(row=row, column=2, padx=(0, 10), pady=pady)

        return lbl

    # --- Toggle sections (DRY) ---
    def _toggle_section(self, name):
        sec = self._sections[name]
        count = self._port_count if name == "ports" else self._net_count
        if sec["expanded"]:
            sec["content"].grid_forget()
            sec["expanded"] = False
        else:
            sec["content"].grid(row=sec["row"], column=0, padx=10,
                                pady=(5, 0), sticky="ew")
            sec["expanded"] = True
        self._update_section_header(name, count)
        self._fit_height()

    def _update_section_header(self, name, count):
        sec = self._sections[name]
        arrow = "\u25BC" if sec["expanded"] else "\u25B6"
        sec["button"].configure(text=f"{arrow}  {sec['label']} ({count})")

    # --- Auto refresh ---
    def _start_auto_refresh(self):
        self._do_refresh()

    def _do_refresh(self):
        threading.Thread(target=self._bg_scan, daemon=True).start()
        self.after(REFRESH_INTERVAL_MS, self._do_refresh)

    def _log_change(self, key, prefix, new_val):
        """Log value change if different from previous. Returns True if changed."""
        old_val = self._prev.get(key, "")
        if new_val != old_val:
            log_device(f"{prefix}: '{old_val}' -> '{new_val}'")
            self._prev[key] = new_val
            return True
        return False

    def _bg_scan(self):
        try:
            serial_ports = get_serial_ports()
            usb_devices = get_usb_devices()

            com_str = ", ".join(p["device"] for p in serial_ports) if serial_ports else "Немає"
            usb_str = ", ".join(usb_devices) if usb_devices else "Немає"

            self._log_change("com", "[COM] Порти змінено", com_str)
            self._log_change("usb", "[USB] Порти змінено", usb_str)

            local_ip = get_local_ip()
            netbird_ip = get_netbird_ip()
            radmin_ip = get_radmin_ip()

            self._log_change("local_ip", "[МЕРЕЖА] Локальний IP змінено", local_ip)
            self._log_change("netbird", "[VPN] NetBird", netbird_ip)
            self._log_change("radmin", "[VPN] Radmin", radmin_ip)

            vpn_on = _is_active_ip(netbird_ip)
            vpn_status = "on" if vpn_on else "off"
            if self._log_change("vpn_status", "[VPN] Статус", vpn_status):
                if vpn_on:
                    log_device(f"[VPN] NetBird ПІДКЛЮЧЕНИЙ | IP: {netbird_ip}")
                else:
                    log_device("[VPN] NetBird ВІДКЛЮЧЕНИЙ")

            self.after(0, lambda: self._update_ui(
                serial_ports, usb_devices,
                local_ip, netbird_ip, radmin_ip, vpn_on
            ))
        except Exception as e:
            log(f"[ERROR] bg_scan failed: {e}")

    def _update_ui(self, serial_ports, usb_devices,
                   local_ip, netbird_ip, radmin_ip, vpn_on):
        # Ports
        scroll_pos = self.ports_text.yview()
        self.ports_text.configure(state="normal")
        self.ports_text.delete("1.0", "end")

        com_shown = 0
        for p in serial_ports:
            status = p.get("status", "")
            if status == "busy":
                status_txt = "зайнятий (програма)"
            elif status == "ready":
                status_txt = "пристрій знайдено"
            elif status == "disconnected":
                status_txt = "відключено"
            else:
                continue
            hwid = p.get("hwid", "")
            self.ports_text.insert("end", f"  {p['device']}  —  {status_txt}  [{hwid}]\n")
            com_shown += 1
        if com_shown == 0:
            self.ports_text.insert("end", "  COM: немає пристроїв\n")

        if usb_devices:
            for d in usb_devices:
                self.ports_text.insert("end", f"  USB: {d}\n")
        else:
            self.ports_text.insert("end", "  USB: немає пристроїв\n")

        self.ports_text.configure(state="disabled")
        self.ports_text.yview_moveto(scroll_pos[0])

        # Update counts and headers
        self._port_count = len(serial_ports) + len(usb_devices)
        self._net_count = sum(1 for ip in [local_ip, netbird_ip, radmin_ip]
                              if _is_active_ip(ip))
        self._update_section_header("ports", self._port_count)
        self._update_section_header("net", self._net_count)

        # Network
        self.lbl_local_ip.configure(text=local_ip)
        self.lbl_netbird.configure(text=netbird_ip)
        self.lbl_radmin.configure(text=radmin_ip)

        # VPN bar
        if vpn_on:
            self.vpn_bar.configure(fg_color=GREEN)
            self.lbl_vpn_status.configure(
                text="VPN активний  |  NetBird пiдключений")
        else:
            self.vpn_bar.configure(fg_color=RED)
            self.lbl_vpn_status.configure(text="NetBird вiдключений")

        self._fit_height()

    # --- Fit height ---
    def _fit_height(self):
        self.update_idletasks()
        cur_w = self.winfo_width()
        req_h = self.winfo_reqheight()
        # Bypass customtkinter scaling — winfo values already in
        # scaled pixels, calling self.geometry() would scale them again
        import tkinter
        tkinter.Tk.geometry(self, f"{cur_w}x{req_h}")

    # --- Copy IP to clipboard ---
    def _copy_ip(self, label):
        ip = label.cget("text")
        if ip and ip != "..." and _is_active_ip(ip):
            self.clipboard_clear()
            self.clipboard_append(ip)
            orig_text = ip
            label.configure(text="Скопійовано!")
            self.after(1000, lambda: label.configure(text=orig_text))

    # --- Load config ---
    def _load_data(self):
        try:
            config, is_new = load_or_fetch_config()
        except Exception as e:
            self.config_data = {}
            self.lbl_pos_id.configure(text=f"Помилка: {e}")
            self.lbl_shop_name.configure(text="")
            log(f"Помилка завантаження конфігу: {e}", "ERROR")
            return

        if is_new or config is None:
            self.config_data = {}
            self.lbl_pos_id.configure(text="Введiть код")
            self.lbl_shop_name.configure(text="")
            self.lbl_phone.configure(text="—")
            self.after(500, self._prompt_code_input)
            return

        self.config_data = config
        self._apply_config()

    def _apply_config(self):
        """Update UI with current config data."""
        pos_id = self.config_data.get("pos_id", "")
        shop_name = self.config_data.get("shop_name", "—")
        self.lbl_pos_id.configure(text=f"#{pos_id}" if pos_id else "—")
        self.lbl_shop_name.configure(text=shop_name)
        self.lbl_phone.configure(
            text=self.config_data.get("support_phone", "—"))
        log(f"Клієнт: #{pos_id} {shop_name} | "
            f"Телефон: {self.config_data.get('support_phone')}")

        tg_link = self.config_data.get("telegram_link", "")
        if tg_link:
            qr_img = generate_qr(tg_link, size=190)
            self._qr_image = ctk.CTkImage(
                light_image=qr_img, dark_image=qr_img, size=(190, 190))
            self.lbl_qr.configure(image=self._qr_image, text="")

    # --- Open logs (password protected) ---
    def _open_logs_with_password(self):
        self.attributes("-topmost", False)
        pwd_dialog = ctk.CTkInputDialog(
            text="Введiть пароль:", title="Доступ до логiв")
        pwd = pwd_dialog.get_input()
        if pwd != EDIT_PASSWORD:
            if pwd is not None:
                log("Невдала спроба доступу до логів", "WARN")
            self.attributes("-topmost", True)
            return
        self._open_log_folder()
        self.attributes("-topmost", True)

    # --- Config editor ---
    def _open_config_editor(self):
        self.attributes("-topmost", False)

        pwd_dialog = ctk.CTkInputDialog(
            text="Введiть пароль:", title="Доступ")
        pwd = pwd_dialog.get_input()
        if pwd != EDIT_PASSWORD:
            if pwd is not None:
                log("Невдала спроба входу до налаштувань", "WARN")
            self.attributes("-topmost", True)
            return

        log("Відкрито редактор налаштувань")
        self._show_code_dialog()

    def _prompt_code_input(self):
        """Show code input dialog (requires password)."""
        self.attributes("-topmost", False)

        pwd_dialog = ctk.CTkInputDialog(
            text="Введiть пароль технiка:", title="Доступ")
        pwd = pwd_dialog.get_input()
        if pwd != EDIT_PASSWORD:
            if pwd is not None:
                log("Невдала спроба входу", "WARN")
            self.attributes("-topmost", True)
            return

        self._show_code_dialog()

    def _show_code_dialog(self):
        """Show dialog for entering POS code."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("LimanSoft — Код торгової точки")
        dialog.geometry("350x220")
        dialog.attributes("-topmost", True)
        dialog.focus_force()
        dialog.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(dialog, text="Введiть код торгової точки (8 символiв):",
                     font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, padx=20, pady=(20, 5))

        entry_code = ctk.CTkEntry(dialog, width=200, justify="center",
                                   font=ctk.CTkFont(size=16))
        entry_code.grid(row=1, column=0, padx=20, pady=(0, 5))
        entry_code.focus()

        # Bind keyboard shortcuts for all layouts (macOS Cyrillic fix)
        _bind_entry_shortcuts(dialog, entry_code)

        # Pre-fill existing code
        existing_code = self.config_data.get("code", "")
        if existing_code:
            entry_code.insert(0, existing_code)

        # Autostart checkbox
        autostart_var = ctk.BooleanVar(value=is_autostart_enabled())
        ctk.CTkCheckBox(dialog, text="Автозапуск з системою",
                        variable=autostart_var,
                        font=ctk.CTkFont(size=12)).grid(
            row=2, column=0, padx=20, pady=(5, 0))

        lbl_error = ctk.CTkLabel(dialog, text="", text_color=RED,
                                  font=ctk.CTkFont(size=11))
        lbl_error.grid(row=3, column=0, padx=20)

        def submit():
            code = entry_code.get().strip().lower()
            if len(code) != 8:
                lbl_error.configure(text="Код має бути 8 символiв")
                return

            lbl_error.configure(text="Завантаження...")
            dialog.update()

            api_data = fetch_from_api(code)
            if api_data:
                save_config(api_data)
                self.config_data = api_data
                self._apply_config()
                try:
                    set_autostart(autostart_var.get())
                    log(f"Автозапуск: {'увімкнено' if autostart_var.get() else 'вимкнено'}")
                except Exception as e:
                    log(f"Помилка автозапуску: {e}", "WARN")
                log(f"Код '{code}' прийнято, дані завантажено з API")
                dialog.destroy()
                self.attributes("-topmost", True)
                self._fit_height()
            else:
                lbl_error.configure(
                    text="Код не знайдено або помилка з'єднання")

        def on_close():
            dialog.destroy()
            self.attributes("-topmost", True)

        dialog.protocol("WM_DELETE_WINDOW", on_close)
        entry_code.bind("<Return>", lambda e: submit())

        ctk.CTkButton(dialog, text="Пiдтвердити", width=160,
                      fg_color=ORANGE, hover_color=DARK_ORANGE,
                      command=submit).grid(row=4, column=0, pady=(5, 20))


def _bind_entry_shortcuts(dialog, entry):
    """Bind Cmd/Ctrl+V/A/C/X for any keyboard layout (macOS Cyrillic fix)."""

    def _paste(event=None):
        try:
            text = dialog.clipboard_get()
            try:
                entry.delete("sel.first", "sel.last")
            except Exception:
                pass
            entry.insert("insert", text)
        except Exception:
            pass
        return "break"

    def _select_all(event=None):
        entry.select_range(0, "end")
        entry.icursor("end")
        return "break"

    def _cut(event=None):
        try:
            text = entry.selection_get()
            dialog.clipboard_clear()
            dialog.clipboard_append(text)
            entry.delete("sel.first", "sel.last")
        except Exception:
            pass
        return "break"

    def _copy(event=None):
        try:
            text = entry.selection_get()
            dialog.clipboard_clear()
            dialog.clipboard_append(text)
        except Exception:
            pass
        return "break"

    actions_by_char = {"v": _paste, "a": _select_all, "c": _copy, "x": _cut}
    # Windows keycodes for V/A/C/X (work regardless of keyboard layout)
    actions_by_keycode = {86: _paste, 65: _select_all, 67: _copy, 88: _cut}

    def _on_key(event):
        # Check Ctrl (0x4) or Cmd (0x8)
        if not (event.state & 0x4 or event.state & 0x8):
            return
        # Try by char first (works on macOS with any layout)
        key = event.char.lower() if event.char else ""
        action = actions_by_char.get(key)
        # Fallback to keycode (works on Windows with non-Latin layouts)
        if not action:
            action = actions_by_keycode.get(event.keycode)
        if action:
            return action(event)

    for widget in (entry, entry._entry):
        widget.bind("<Key>", _on_key)

    # Right-click context menu
    menu = tkinter.Menu(dialog, tearoff=0)
    menu.add_command(label="Вставити", command=_paste)
    menu.add_command(label="Копiювати", command=_copy)
    menu.add_command(label="Вирiзати", command=_cut)
    menu.add_separator()
    menu.add_command(label="Видiлити все", command=_select_all)

    def _show_menu(event):
        menu.tk_popup(event.x_root, event.y_root)

    for widget in (entry, entry._entry):
        widget.bind("<Button-3>", _show_menu)
        # macOS right-click (Ctrl+Click)
        widget.bind("<Button-2>", _show_menu)
