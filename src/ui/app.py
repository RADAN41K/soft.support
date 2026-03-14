import os
import platform
import sys
import threading
import customtkinter as ctk
from PIL import Image, ImageTk

from src.config import get_base_path, load_or_fetch_config, fetch_from_api, save_config
from src.utils.qr import generate_qr
from src.utils.ports import get_serial_ports, get_usb_devices
from src.utils.network import get_local_ip, get_netbird_ip, get_radmin_ip
from src.utils.logging import log, log_device

EDIT_PASSWORD = "258456"
REFRESH_INTERVAL_MS = 3000


class SoftSupportApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("LimanSoft — Support")
        self.minsize(340, 200)
        self.geometry("380x200")
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
        self.INACTIVE_VALUES = (
            "Н/Д", "—", "Не підключений", "Не подключён",
            "Не установлен", "Не определён",
        )

        self.config_data = {}
        self._qr_image = None
        self._ports_expanded = False
        self._net_expanded = False
        self._tray_icon = None
        self._tray_thread = None
        self._macos_tray = False

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
        self.resizable(True, False)
        self.after(100, self._fit_height)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        log("Форму запущено, додаток готовий до роботи")

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
        if os.path.exists(icon_png):
            img = Image.open(icon_png)
            self._icon = ImageTk.PhotoImage(img)
            self.iconphoto(True, self._icon)
            self._icon_path = icon_png

    # --- System tray ---
    def _create_tray_icon(self):
        """Create and return pystray Icon instance."""
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
        return pystray.Icon(
            "SoftSupport", tray_image,
            "LimanSoft Технічна підтримка", menu
        )

    def _setup_tray(self):
        try:
            if platform.system() == "Darwin":
                # macOS: pystray crashes with tkinter (GIL/AppKit conflict)
                # Minimize to dock instead of tray
                log("macOS: сворачування у Dock замість трею")
                return
            self._tray_icon = self._create_tray_icon()
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
        if self._tray_icon:
            self.withdraw()
            log("Вікно приховано в трей")
        elif platform.system() == "Darwin":
            self.iconify()
            log("Вікно згорнуто у Dock")
        else:
            self._quit_app()

    # --- UI ---
    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        for i in range(8):
            self.grid_rowconfigure(i, weight=0)

        row = 0

        # --- Block 1: Client / Branding ---
        self.client_frame = ctk.CTkFrame(self, fg_color=self.ORANGE, corner_radius=10)
        self.client_frame.grid(row=row, column=0, padx=10, pady=(10, 0), sticky="ew")
        self.client_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.client_frame, text="Технiчна пiдтримка LimanSoft",
                     font=ctk.CTkFont(size=17, weight="bold"),
                     text_color=self.WHITE).grid(
            row=0, column=0, padx=10, pady=(6, 0))

        ctk.CTkLabel(self.client_frame, text="Скануйте QR-код LimanSoft Help 24/7",
                     font=ctk.CTkFont(size=13),
                     text_color=self.WHITE).grid(
            row=1, column=0, padx=10, pady=(1, 0))

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
                                    fg_color=self.WHITE, corner_radius=6)
        self.lbl_qr.grid(row=0, column=1, padx=(0, 10), pady=0)

        right = ctk.CTkFrame(self.info_frame, fg_color="transparent")
        right.grid(row=0, column=2)

        self.lbl_client_id = ctk.CTkLabel(right, text="—",
                                           font=ctk.CTkFont(size=16, weight="bold"),
                                           text_color=self.WHITE)
        self.lbl_client_id.grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(right, text="Номер тех.пiдтримки:",
                     font=ctk.CTkFont(size=10),
                     text_color="#FFD5B0").grid(row=1, column=0, sticky="w")

        self.lbl_phone = ctk.CTkLabel(right, text="—",
                                       font=ctk.CTkFont(size=15),
                                       text_color=self.WHITE)
        self.lbl_phone.grid(row=2, column=0, sticky="w")

        self.btn_edit = ctk.CTkButton(
            right, text="Редагувати", width=80, height=22,
            fg_color=self.DARK_ORANGE, hover_color="#CC5500",
            font=ctk.CTkFont(size=10),
            command=self._open_config_editor)
        self.btn_edit.grid(row=3, column=0, sticky="w", pady=(4, 0))

        # Spacer right
        ctk.CTkFrame(self.info_frame, fg_color="transparent", width=1).grid(
            row=0, column=3)

        row += 1

        # --- Block 2: Ports (collapsible) ---
        self.ports_header = ctk.CTkFrame(self, fg_color=self.WHITE, border_width=1,
                                          border_color="#E0E0E0", corner_radius=10)
        self.ports_header.grid(row=row, column=0, padx=10, pady=(10, 0), sticky="ew")
        self.ports_header.grid_columnconfigure(0, weight=1)

        self.btn_toggle_ports = ctk.CTkButton(
            self.ports_header, text="\u25B6  USB / COM порти",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="transparent", hover_color="#F0F0F0",
            text_color=self.TEXT_DARK, anchor="w",
            command=self._toggle_ports)
        self.btn_toggle_ports.grid(row=0, column=0, padx=5, pady=6, sticky="ew")

        row += 1

        self.ports_content = ctk.CTkFrame(self, fg_color=self.WHITE, border_width=1,
                                           border_color="#E0E0E0", corner_radius=10)
        self.ports_content.grid_columnconfigure(0, weight=1)
        self._ports_row = row

        self.ports_text = ctk.CTkTextbox(self.ports_content, height=100)
        self.ports_text.grid(row=0, column=0, padx=10, pady=(5, 8), sticky="ew")

        row += 1

        # --- Block 3: Network (collapsible) ---
        self.net_header = ctk.CTkFrame(self, fg_color=self.WHITE, border_width=1,
                                        border_color="#E0E0E0", corner_radius=10)
        self.net_header.grid(row=row, column=0, padx=10, pady=(10, 0), sticky="ew")
        self.net_header.grid_columnconfigure(0, weight=1)

        self.btn_toggle_net = ctk.CTkButton(
            self.net_header, text="\u25B6  Мережа",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="transparent", hover_color="#F0F0F0",
            text_color=self.TEXT_DARK, anchor="w",
            command=self._toggle_net)
        self.btn_toggle_net.grid(row=0, column=0, padx=5, pady=6, sticky="ew")

        row += 1

        self.net_content = ctk.CTkFrame(self, fg_color=self.WHITE, border_width=1,
                                         border_color="#E0E0E0", corner_radius=10)
        self.net_content.grid_columnconfigure(1, weight=1)
        self._net_row = row

        ctk.CTkLabel(self.net_content, text="Локальний IP:",
                     text_color=self.TEXT_DARK).grid(
            row=0, column=0, padx=10, pady=2, sticky="w")
        self.lbl_local_ip = ctk.CTkLabel(self.net_content, text="...",
                                          text_color=self.TEXT_DARK)
        self.lbl_local_ip.grid(row=0, column=1, padx=10, pady=2, sticky="w")
        self.btn_copy_local = ctk.CTkButton(
            self.net_content, text="📋", width=28, height=22,
            fg_color="#E0E0E0", hover_color="#D0D0D0", text_color=self.TEXT_DARK,
            font=ctk.CTkFont(size=12),
            command=lambda: self._copy_ip(self.lbl_local_ip))
        self.btn_copy_local.grid(row=0, column=2, padx=(0, 10), pady=2)

        ctk.CTkLabel(self.net_content, text="NetBird IP:",
                     text_color=self.TEXT_DARK).grid(
            row=1, column=0, padx=10, pady=2, sticky="w")
        self.lbl_netbird = ctk.CTkLabel(self.net_content, text="...",
                                         text_color=self.TEXT_DARK)
        self.lbl_netbird.grid(row=1, column=1, padx=10, pady=2, sticky="w")
        self.btn_copy_nb = ctk.CTkButton(
            self.net_content, text="📋", width=28, height=22,
            fg_color="#E0E0E0", hover_color="#D0D0D0", text_color=self.TEXT_DARK,
            font=ctk.CTkFont(size=12),
            command=lambda: self._copy_ip(self.lbl_netbird))
        self.btn_copy_nb.grid(row=1, column=2, padx=(0, 10), pady=2)

        ctk.CTkLabel(self.net_content, text="Radmin IP:",
                     text_color=self.TEXT_DARK).grid(
            row=2, column=0, padx=10, pady=(2, 8), sticky="w")
        self.lbl_radmin = ctk.CTkLabel(self.net_content, text="...",
                                        text_color=self.TEXT_DARK)
        self.lbl_radmin.grid(row=2, column=1, padx=10, pady=(2, 8), sticky="w")
        self.btn_copy_radmin = ctk.CTkButton(
            self.net_content, text="📋", width=28, height=22,
            fg_color="#E0E0E0", hover_color="#D0D0D0", text_color=self.TEXT_DARK,
            font=ctk.CTkFont(size=12),
            command=lambda: self._copy_ip(self.lbl_radmin))
        self.btn_copy_radmin.grid(row=2, column=2, padx=(0, 10), pady=(2, 8))

        row += 1

        # --- VPN Status bar ---
        self.vpn_bar = ctk.CTkFrame(self, fg_color=self.GREEN, corner_radius=10, height=32)
        self.vpn_bar.grid(row=row, column=0, padx=10, pady=(10, 10), sticky="ew")
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
        try:
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

            vpn_on = (netbird_ip not in self.INACTIVE_VALUES
                      and not netbird_ip.startswith("Помилка")
                      and not netbird_ip.startswith("Не "))
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
        except Exception as e:
            log(f"[ERROR] bg_scan failed: {e}")

    def _update_ui(self, serial_ports, usb_devices,
                   local_ip, netbird_ip, radmin_ip, vpn_on):
        # Ports
        self.ports_text.configure(state="normal")
        self.ports_text.delete("1.0", "end")

        if serial_ports:
            for p in serial_ports:
                self.ports_text.insert("end", f"  {p['device']}\n")
        else:
            self.ports_text.insert("end", "  COM: немає пристроїв\n")

        if usb_devices:
            for d in usb_devices:
                self.ports_text.insert("end", f"  USB: {d}\n")
        else:
            self.ports_text.insert("end", "  USB: немає пристроїв\n")

        self.ports_text.configure(state="disabled")

        # Update ports header with count
        port_count = len(serial_ports) + len(usb_devices)
        arrow = "\u25BC" if self._ports_expanded else "\u25B6"
        self.btn_toggle_ports.configure(
            text=f"{arrow}  USB / COM порти ({port_count})")

        # Network
        self.lbl_local_ip.configure(text=local_ip)
        self.lbl_netbird.configure(text=netbird_ip)
        self.lbl_radmin.configure(text=radmin_ip)

        # Update network header with count
        net_count = sum(1 for ip in [local_ip, netbird_ip, radmin_ip]
                        if ip not in self.INACTIVE_VALUES
                        and not ip.startswith("Помилка")
                        and not ip.startswith("Не "))
        arrow = "\u25BC" if self._net_expanded else "\u25B6"
        self.btn_toggle_net.configure(
            text=f"{arrow}  Мережа ({net_count})")

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
        cur_w = self.winfo_width()
        req_h = self.winfo_reqheight()
        self.geometry(f"{cur_w}x{req_h}")

    # --- Copy IP to clipboard ---
    def _copy_ip(self, label):
        ip = label.cget("text")
        if ip and ip != "..." and not ip.startswith("Не "):
            self.clipboard_clear()
            self.clipboard_append(ip)
            # Brief visual feedback
            orig_text = label.cget("text")
            label.configure(text="Скопійовано!")
            self.after(1000, lambda: label.configure(text=orig_text))

    # --- Toggle sections ---
    def _toggle_ports(self):
        # Extract current count from button text
        cur = self.btn_toggle_ports.cget("text")
        count_part = cur[cur.rfind("("):] if "(" in cur else ""
        if self._ports_expanded:
            self.ports_content.grid_forget()
            self.btn_toggle_ports.configure(
                text=f"\u25B6  USB / COM порти {count_part}".rstrip())
            self._ports_expanded = False
        else:
            self.ports_content.grid(row=self._ports_row, column=0, padx=10,
                                    pady=(5, 0), sticky="ew")
            self.btn_toggle_ports.configure(
                text=f"\u25BC  USB / COM порти {count_part}".rstrip())
            self._ports_expanded = True
        self._fit_height()

    def _toggle_net(self):
        cur = self.btn_toggle_net.cget("text")
        count_part = cur[cur.rfind("("):] if "(" in cur else ""
        if self._net_expanded:
            self.net_content.grid_forget()
            self.btn_toggle_net.configure(
                text=f"\u25B6  Мережа {count_part}".rstrip())
            self._net_expanded = False
        else:
            self.net_content.grid(row=self._net_row, column=0, padx=10,
                                  pady=(5, 0), sticky="ew")
            self.btn_toggle_net.configure(
                text=f"\u25BC  Мережа {count_part}".rstrip())
            self._net_expanded = True
        self._fit_height()

    # --- Load config ---
    def _load_data(self):
        try:
            config, is_new = load_or_fetch_config()
        except Exception as e:
            self.config_data = {}
            self.lbl_client_id.configure(text=f"Помилка: {e}")
            log(f"Помилка завантаження конфігу: {e}", "ERROR")
            return

        if is_new or config is None:
            # No config — prompt for code
            self.config_data = {}
            self.lbl_client_id.configure(text="Введiть код")
            self.lbl_phone.configure(text="—")
            self.after(500, self._prompt_code_input)
            return

        self.config_data = config
        self._apply_config()

    def _apply_config(self):
        """Update UI with current config data."""
        pos_id = self.config_data.get("pos_id", "")
        shop_name = self.config_data.get("shop_name", "—")
        display_name = f"#{pos_id} {shop_name}" if pos_id else shop_name
        self.lbl_client_id.configure(text=display_name)
        self.lbl_phone.configure(
            text=self.config_data.get("support_phone", "—"))
        log(f"Клієнт: {display_name} | "
            f"Телефон: {self.config_data.get('support_phone')}")

        tg_link = self.config_data.get("telegram_link", "")
        if tg_link:
            qr_img = generate_qr(tg_link, size=140)
            self._qr_image = ctk.CTkImage(
                light_image=qr_img, dark_image=qr_img, size=(140, 140))
            self.lbl_qr.configure(image=self._qr_image, text="")

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
        dialog.geometry("350x180")
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

        # Fix paste with non-Latin keyboard layouts (Ctrl+V / Cmd+V)
        def _paste(event):
            try:
                text = dialog.clipboard_get()
                entry_code.delete(0, "end")
                entry_code.insert(0, text)
            except Exception:
                pass
            return "break"

        entry_code.bind("<Control-v>", _paste)
        entry_code.bind("<Control-V>", _paste)
        entry_code.bind("<Command-v>", _paste)
        entry_code.bind("<Command-V>", _paste)

        # Pre-fill existing code if any
        existing_code = self.config_data.get("code", "")
        if existing_code:
            entry_code.insert(0, existing_code)

        self.lbl_code_error = ctk.CTkLabel(dialog, text="",
                                            text_color=self.RED,
                                            font=ctk.CTkFont(size=11))
        self.lbl_code_error.grid(row=2, column=0, padx=20)

        def submit():
            code = entry_code.get().strip().lower()
            if len(code) != 8:
                self.lbl_code_error.configure(text="Код має бути 8 символiв")
                return

            self.lbl_code_error.configure(text="Завантаження...")
            dialog.update()

            api_data = fetch_from_api(code)
            if api_data:
                save_config(api_data)
                self.config_data = api_data
                self._apply_config()
                log(f"Код '{code}' прийнято, дані завантажено з API")
                dialog.destroy()
                self.attributes("-topmost", True)
                self._fit_height()
            else:
                self.lbl_code_error.configure(text="Код не знайдено або помилка з'єднання")

        def on_close():
            dialog.destroy()
            self.attributes("-topmost", True)

        dialog.protocol("WM_DELETE_WINDOW", on_close)
        entry_code.bind("<Return>", lambda e: submit())

        ctk.CTkButton(dialog, text="Пiдтвердити", width=160,
                      fg_color=self.ORANGE, hover_color=self.DARK_ORANGE,
                      command=submit).grid(row=3, column=0, pady=(5, 20))

    # --- Config editor ---
    def _open_config_editor(self):
        # Temporarily disable topmost so dialogs are interactive
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
