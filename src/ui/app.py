import multiprocessing
import os
import platform
import queue
import re
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
from src.utils.logging import log, get_log_dir
from src.utils.autostart import is_autostart_enabled, set_autostart
from src.utils.updater import check_and_apply_silently
from src.utils.watcher import DeviceWatcher

EDIT_PASSWORD = "258456"

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


def _macos_set_activation_policy(policy):
    """Set NSApplication activation policy via ctypes (no PyObjC).
    0 = Regular (Dock icon visible), 1 = Accessory (no Dock icon).
    """
    try:
        from ctypes import cdll, util, c_void_p, c_long, CFUNCTYPE
        lib = cdll.LoadLibrary(util.find_library("objc"))
        lib.objc_getClass.restype = c_void_p
        lib.sel_registerName.restype = c_void_p
        send = CFUNCTYPE(c_void_p, c_void_p, c_void_p)(
            ("objc_msgSend", lib))
        send_long = CFUNCTYPE(c_void_p, c_void_p, c_void_p, c_long)(
            ("objc_msgSend", lib))
        ns_app = send(
            lib.objc_getClass(b"NSApplication"),
            lib.sel_registerName(b"sharedApplication"))
        send_long(ns_app, lib.sel_registerName(b"setActivationPolicy:"), policy)
        if policy == 0:
            send_long(ns_app, lib.sel_registerName(
                b"activateIgnoringOtherApps:"), 1)
    except Exception:
        pass


def _macos_tray_worker(icon_path, cmd_queue):
    """Run pystray in a separate process (macOS only)."""
    _macos_set_activation_policy(1)
    import pystray
    from PIL import Image as PILImage

    if icon_path and os.path.exists(icon_path):
        img = PILImage.open(icon_path).convert("RGBA")
    else:
        img = PILImage.new("RGB", (64, 64), "#FF6600")

    def on_show(*_):
        cmd_queue.put("show")

    def on_logs(*_):
        cmd_queue.put("logs")

    def on_quit(*_):
        cmd_queue.put("quit")
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Показати", on_show, default=True),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Вiдкрити логи", on_logs),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Закрити", on_quit),
    )
    icon = pystray.Icon(
        "SoftSupport", img, "LimanSoft Технiчна пiдтримка", menu)

    # Monkey-patch: pystray renders at 1x, causing blur on Retina.
    # Override to render at 2x pixels and set NSImage logical size.
    _orig_assert = icon._assert_image

    def _retina_assert_image():
        import io as _io
        thickness = icon._status_bar.thickness()
        px_size = (int(thickness * 2), int(thickness * 2))
        pt_size = (int(thickness), int(thickness))

        if icon._icon_image:
            return

        source = icon._icon.resize(px_size, PILImage.LANCZOS)
        b = _io.BytesIO()
        source.save(b, "png")

        import AppKit, Foundation
        data = Foundation.NSData(b.getvalue())
        icon._icon_image = AppKit.NSImage.alloc().initWithData_(data)
        icon._icon_image.setSize_(pt_size)
        icon._status_item.button().setImage_(icon._icon_image)

    icon._assert_image = _retina_assert_image
    icon.run()


class SoftSupportApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        if platform.system() == "Darwin":
            _macos_set_activation_policy(1)

        self.title(f"LimanSoft Support v{__version__}")
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
        self._ui_queue = queue.Queue()

        # Collapsible sections state: {name: (button, content, row, expanded)}
        self._sections = {}
        self._port_count = 0
        self._scan_error = False
        self._net_count = 0

        # Previous values for change detection
        self._prev = {}

        self._build_ui()
        self._load_data()
        self._setup_tray()
        self._start_watcher()
        self.resizable(True, False)
        self.after(300, self._fit_height)
        self.after(1000, self._fit_height)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # Windows — start minimized to tray; macOS/Linux — show window
        if platform.system() == "Windows":
            self.withdraw()
            log(f"Форму запущено v{__version__}, додаток готовий до роботи (згорнуто в трей)")
        else:
            log(f"Форму запущено v{__version__}, додаток готовий до роботи")

        # Check for updates silently in background
        check_and_apply_silently()
        self._poll_ui_queue()

    def _run_on_ui(self, callback):
        """Thread-safe: schedule callback on the main thread."""
        self._ui_queue.put(callback)

    def _poll_ui_queue(self):
        """Process pending UI callbacks from background threads."""
        try:
            while True:
                self._ui_queue.get_nowait()()
        except queue.Empty:
            pass
        self.after(50, self._poll_ui_queue)

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
            img = Image.open(icon_png).convert("RGBA")
            self._icon = ImageTk.PhotoImage(img)
            self.iconphoto(True, self._icon)
        if os.path.exists(icon_png):
            self._icon_path = icon_png

    # --- System tray ---
    def _setup_tray(self):
        if platform.system() == "Darwin":
            self._setup_tray_macos()
            return
        try:
            import pystray
            icon_path = getattr(self, "_icon_path", None)
            if icon_path and os.path.exists(icon_path):
                tray_image = Image.open(icon_path).convert("RGBA").resize((256, 256), Image.LANCZOS)
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

    def _setup_tray_macos(self):
        """Start pystray in a separate process (avoids AppKit+tkinter crash)."""
        try:
            icon_path = getattr(self, "_icon_path", None)
            self._tray_queue = multiprocessing.Queue()
            self._tray_process = multiprocessing.Process(
                target=_macos_tray_worker,
                args=(icon_path, self._tray_queue),
                daemon=True,
            )
            self._tray_process.start()
            self._tray_icon = True
            self.after(200, self._poll_tray_queue)
            log("Іконку меню-бару запущено (macOS, окремий процес)")
        except Exception as e:
            log(f"Меню-бар недоступний: {e}", "WARN")

    def _poll_tray_queue(self):
        """Check for commands from the macOS tray process."""
        try:
            while not self._tray_queue.empty():
                cmd = self._tray_queue.get_nowait()
                if cmd == "show":
                    self._show_window()
                elif cmd == "logs":
                    self._open_log_folder()
                elif cmd == "quit":
                    self._tray_quit()
                    return
        except Exception:
            pass
        self.after(200, self._poll_tray_queue)

    def _tray_show(self, *_args):
        self._run_on_ui(self._show_window)

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
        log(f"[ПК] Програма зупинена користувачем "
                   f"{os.environ.get('USERNAME', os.environ.get('USER', '?'))}")
        if hasattr(self, "_tray_process") and self._tray_process.is_alive():
            self._tray_process.terminate()
        elif self._tray_icon and hasattr(self._tray_icon, "stop"):
            self._tray_icon.stop()
        self._run_on_ui(self.destroy)

    def _show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()
        if platform.system() == "Darwin":
            _macos_set_activation_policy(1)

    def _on_close(self):
        if self._tray_icon:
            self.withdraw()
            log("Вікно приховано в трей")
        else:
            self.iconify()
            log("Вікно згорнуто")

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

        # Right-click context menu for ports textbox
        self._ports_menu = tkinter.Menu(self, tearoff=0)
        self._ports_menu.add_command(label="Копiювати", command=self._copy_ports_selection)
        self._ports_menu.add_command(label="Копiювати все", command=self._copy_ports_all)

        def _show_ports_menu(event):
            self._ports_menu.tk_popup(event.x_root, event.y_root)

        self.ports_text._textbox.bind("<Button-3>", _show_ports_menu)
        self.ports_text._textbox.bind("<Button-2>", _show_ports_menu)

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

        # Scan indicator dot (ports section only)
        dot_label = None
        if name == "ports":
            dot_label = ctk.CTkLabel(
                header, text="\u25CF", font=ctk.CTkFont(size=10),
                text_color=BORDER_COLOR, fg_color="transparent", width=16)
            dot_label.grid(row=0, column=1, padx=(0, 10))

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
            "dot": dot_label,
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
        if name == "ports" and sec.get("dot"):
            if self._scanning_devices:
                color = ORANGE
            elif self._scan_error:
                color = "#DC2626"
            else:
                color = GREEN
            sec["dot"].configure(text_color=color)

    # --- Event-driven refresh ---
    def _start_watcher(self):
        self._scanning_devices = False
        self._scanning_network = False
        self._watcher = DeviceWatcher(
            on_device_change=lambda: self._run_on_ui(self._trigger_device_scan),
            on_network_change=lambda: self._run_on_ui(self._trigger_network_scan),
        )
        self._watcher.start()
        # Initial scan after mainloop starts
        self.after(100, self._trigger_device_scan)
        self.after(100, self._trigger_network_scan)

    def _trigger_device_scan(self):
        if not self._scanning_devices:
            self._scanning_devices = True
            self._update_section_header("ports", self._port_count)
            threading.Thread(
                target=self._bg_scan_devices, daemon=True).start()

    def _trigger_network_scan(self):
        if not self._scanning_network:
            self._scanning_network = True
            threading.Thread(
                target=self._bg_scan_network, daemon=True).start()

    def _log_change(self, key, prefix, new_val):
        """Log value change if different from previous. Returns True if changed."""
        old_val = self._prev.get(key, "")
        if new_val != old_val:
            log(f"{prefix}: '{old_val}' -> '{new_val}'")
            self._prev[key] = new_val
            return True
        return False

    def _bg_scan_devices(self):
        try:
            self._scan_error = False
            serial_ports = get_serial_ports()
            usb_devices, usb_all = get_usb_devices()

            usb_all_keys = frozenset(usb_all)
            old_usb_all = self._prev.get("usb_all", frozenset())

            if usb_all_keys != old_usb_all:
                for d in sorted(usb_all_keys):
                    log(f"[USB] {d}")
                if not usb_all_keys:
                    log("[USB] Немає")
                self._prev["usb_all"] = usb_all_keys

            self._run_on_ui(lambda: self._update_ports_ui(
                serial_ports, usb_devices))
        except Exception as e:
            log(f"[ERROR] device scan failed: {e}")
            self._scan_error = True
        finally:
            self._scanning_devices = False
            self._run_on_ui(lambda: self._update_section_header(
                "ports", self._port_count))

    def _bg_scan_network(self):
        try:
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
                    log(f"[VPN] NetBird ПІДКЛЮЧЕНИЙ | IP: {netbird_ip}")
                else:
                    log("[VPN] NetBird ВІДКЛЮЧЕНИЙ")

            self._run_on_ui(lambda: self._update_network_ui(
                local_ip, netbird_ip, radmin_ip, vpn_on))
        except Exception as e:
            log(f"[ERROR] network scan failed: {e}")
        finally:
            self._scanning_network = False

    def _update_ports_ui(self, serial_ports, usb_devices):
        lines = []
        com_shown = 0
        for p in serial_ports:
            status = p.get("status", "")
            hwid = p.get("hwid", "")
            if status == "busy":
                status_txt = "зайнятий (програма)"
            elif status == "ready":
                status_txt = "пристрій знайдено"
            elif status == "disconnected":
                status_txt = "відключено"
            elif status == "empty":
                status_txt = "вільний (без програми)"
            else:
                continue
            lines.append(f"  {p['device']}: {status_txt}  [{hwid}]")
            com_shown += 1
        if com_shown == 0:
            lines.append("  COM: портів не знайдено")

        if usb_devices:
            for i, d in enumerate(usb_devices, 1):
                m = re.match(r'(USB\d+)', d)
                if m:
                    lines.append(f"  {m.group(1)}")
                else:
                    lines.append(f"  USB{i}")
        else:
            lines.append("  USB: немає пристроїв")

        new_text = "\n".join(lines)
        old_text = self.ports_text.get("1.0", "end-1c")
        if new_text != old_text:
            self.ports_text.configure(state="normal")
            self.ports_text.delete("1.0", "end")
            self.ports_text.insert("end", new_text)
            self.ports_text.configure(state="disabled")

        self._port_count = com_shown + len(usb_devices)
        self._update_section_header("ports", self._port_count)

    def _update_network_ui(self, local_ip, netbird_ip, radmin_ip, vpn_on):
        self.lbl_local_ip.configure(text=local_ip)
        self.lbl_netbird.configure(text=netbird_ip)
        self.lbl_radmin.configure(text=radmin_ip)

        self._net_count = sum(1 for ip in [local_ip, netbird_ip, radmin_ip]
                              if _is_active_ip(ip))
        self._update_section_header("net", self._net_count)

        if vpn_on:
            self.vpn_bar.configure(fg_color=GREEN)
            self.lbl_vpn_status.configure(
                text="VPN активний  |  NetBird пiдключений")
        else:
            self.vpn_bar.configure(fg_color=RED)
            self.lbl_vpn_status.configure(text="NetBird вiдключений")

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
    def _copy_ports_selection(self):
        """Copy selected text from ports textbox."""
        try:
            text = self.ports_text.selection_get()
            self.clipboard_clear()
            self.clipboard_append(text)
        except Exception:
            pass

    def _copy_ports_all(self):
        """Copy all text from ports textbox."""
        text = self.ports_text.get("1.0", "end-1c")
        if text.strip():
            self.clipboard_clear()
            self.clipboard_append(text)

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

    # --- Password dialog ---
    def _ask_password(self, title="Доступ", text="Введiть пароль:"):
        """Show password dialog with masked input. Returns entered string or None."""
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.geometry("300x150")
        dialog.resizable(False, False)
        dialog.grab_set()
        dialog.attributes("-topmost", True)

        result = [None]

        ctk.CTkLabel(dialog, text=text).pack(pady=(20, 5))
        entry = ctk.CTkEntry(dialog, show="*", width=200)
        entry.pack(pady=5)
        entry.focus_force()

        def on_ok(*_):
            result[0] = entry.get()
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        entry.bind("<Return>", on_ok)
        ctk.CTkButton(dialog, text="OK", command=on_ok, width=100).pack(pady=10)
        dialog.protocol("WM_DELETE_WINDOW", on_cancel)
        dialog.wait_window()
        return result[0]

    # --- Open logs (password protected) ---
    def _open_logs_with_password(self):
        self.attributes("-topmost", False)
        pwd = self._ask_password(title="Доступ до логiв")
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
        pwd = self._ask_password()
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
        pwd = self._ask_password(text="Введiть пароль технiка:")
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
        # Ctrl = 0x4, but NumLock adds 0x8 on Windows, CapsLock adds 0x2
        # Cmd on macOS = 0x8 (no conflict - NumLock not used)
        ctrl = event.state & 0x4 and not (event.state & 0x20000)
        cmd = event.state & 0x8 and platform.system() == "Darwin"
        if not (ctrl or cmd):
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
