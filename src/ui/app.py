import threading
import customtkinter as ctk
from PIL import Image

from src.config import load_config
from src.utils.qr import generate_qr
from src.utils.ports import get_serial_ports, get_usb_devices
from src.utils.network import get_local_ip, get_netbird_ip, get_radmin_ip


class SoftSupportApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Soft Support — LimanSoft")
        self.minsize(340, 200)
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color="#FFFFFF")

        # Brand colors
        self.ORANGE = "#FF6600"
        self.DARK_ORANGE = "#E55C00"
        self.WHITE = "#FFFFFF"
        self.TEXT_DARK = "#333333"

        self.config_data = {}
        self._qr_image = None  # prevent GC
        self._ports_expanded = True
        self._net_expanded = True

        self._build_ui()
        self._load_data()
        self.after(100, self._fit_height)

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)  # branding
        self.grid_rowconfigure(1, weight=0)  # ports header
        self.grid_rowconfigure(2, weight=0)  # ports content
        self.grid_rowconfigure(3, weight=0)  # net header
        self.grid_rowconfigure(4, weight=0)  # net content

        # --- Block 1: Client / Branding ---
        self.client_frame = ctk.CTkFrame(self, fg_color=self.ORANGE, corner_radius=10)
        self.client_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")
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
        self.info_frame.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="ew")
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
        self.lbl_phone.grid(row=2, column=0, pady=(0, 5))

        # --- Block 2: Ports (collapsible) ---
        # Header (always visible)
        self.ports_header = ctk.CTkFrame(self, fg_color=self.WHITE, border_width=1,
                                          border_color="#E0E0E0", corner_radius=10)
        self.ports_header.grid(row=1, column=0, padx=10, pady=(5, 0), sticky="ew")
        self.ports_header.grid_columnconfigure(0, weight=1)

        self.btn_toggle_ports = ctk.CTkButton(
            self.ports_header, text="\u25BC  USB / COM порти", width=200,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="transparent", hover_color="#F0F0F0",
            text_color=self.TEXT_DARK, anchor="w",
            command=self._toggle_ports)
        self.btn_toggle_ports.grid(row=0, column=0, padx=5, pady=6, sticky="w")

        # Content (visible by default)
        self.ports_content = ctk.CTkFrame(self, fg_color=self.WHITE, border_width=1,
                                           border_color="#E0E0E0",
                                           corner_radius=0)
        self.ports_content.grid(row=2, column=0, padx=10, pady=(0, 0), sticky="ew")
        self.ports_content.grid_columnconfigure(0, weight=1)

        ports_inner = ctk.CTkFrame(self.ports_content, fg_color="transparent")
        ports_inner.grid(row=0, column=0, padx=10, pady=(5, 5), sticky="ew")
        ports_inner.grid_columnconfigure(0, weight=1)

        self.btn_refresh_ports = ctk.CTkButton(
            ports_inner, text="Оновити", width=80, height=26,
            fg_color=self.ORANGE, hover_color=self.DARK_ORANGE,
            font=ctk.CTkFont(size=11),
            command=self._refresh_ports)
        self.btn_refresh_ports.grid(row=0, column=1, sticky="e")

        self.ports_text = ctk.CTkTextbox(self.ports_content, height=100)
        self.ports_text.grid(row=1, column=0, padx=10, pady=(0, 8), sticky="ew")

        # --- Block 3: Network (collapsible) ---
        # Header (always visible)
        self.net_header = ctk.CTkFrame(self, fg_color=self.WHITE, border_width=1,
                                        border_color="#E0E0E0", corner_radius=10)
        self.net_header.grid(row=3, column=0, padx=10, pady=(5, 0), sticky="ew")
        self.net_header.grid_columnconfigure(0, weight=1)

        self.btn_toggle_net = ctk.CTkButton(
            self.net_header, text="\u25BC  Мережа", width=200,
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="transparent", hover_color="#F0F0F0",
            text_color=self.TEXT_DARK, anchor="w",
            command=self._toggle_net)
        self.btn_toggle_net.grid(row=0, column=0, padx=5, pady=6, sticky="w")

        # Content (visible by default)
        self.net_content = ctk.CTkFrame(self, fg_color=self.WHITE, border_width=1,
                                         border_color="#E0E0E0",
                                         corner_radius=0)
        self.net_content.grid_columnconfigure(1, weight=1)

        net_inner = ctk.CTkFrame(self.net_content, fg_color="transparent")
        net_inner.grid(row=0, column=0, columnspan=2, padx=10, pady=(5, 2), sticky="ew")
        net_inner.grid_columnconfigure(0, weight=1)

        self.btn_refresh_net = ctk.CTkButton(
            net_inner, text="Оновити", width=80, height=26,
            fg_color=self.ORANGE, hover_color=self.DARK_ORANGE,
            font=ctk.CTkFont(size=11),
            command=self._refresh_network)
        self.btn_refresh_net.grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(self.net_content, text="Локальний IP:",
                     text_color=self.TEXT_DARK).grid(
            row=1, column=0, padx=10, pady=2, sticky="w")
        self.lbl_local_ip = ctk.CTkLabel(self.net_content, text="...",
                                          text_color=self.TEXT_DARK)
        self.lbl_local_ip.grid(row=1, column=1, padx=10, pady=2, sticky="w")

        ctk.CTkLabel(self.net_content, text="NetBird IP:",
                     text_color=self.TEXT_DARK).grid(
            row=2, column=0, padx=10, pady=2, sticky="w")
        self.lbl_netbird = ctk.CTkLabel(self.net_content, text="...",
                                         text_color=self.TEXT_DARK)
        self.lbl_netbird.grid(row=2, column=1, padx=10, pady=2, sticky="w")

        ctk.CTkLabel(self.net_content, text="Radmin IP:",
                     text_color=self.TEXT_DARK).grid(
            row=3, column=0, padx=10, pady=(2, 8), sticky="w")
        self.lbl_radmin = ctk.CTkLabel(self.net_content, text="...",
                                        text_color=self.TEXT_DARK)
        self.lbl_radmin.grid(row=3, column=1, padx=10, pady=(2, 8), sticky="w")

        # Show net content by default
        self.net_content.grid(row=4, column=0, padx=10, pady=(0, 0), sticky="ew")

        # Bottom spacer (same padding as sides)
        spacer = ctk.CTkFrame(self, fg_color="transparent", height=10)
        spacer.grid(row=5, column=0, sticky="ew")

    def _fit_height(self):
        """Auto-resize window height to fit content."""
        self.update_idletasks()
        req_w = max(self.winfo_reqwidth(), self.winfo_width(), 380)
        req_h = self.winfo_reqheight()
        self.geometry(f"{req_w}x{req_h}")

    def _toggle_ports(self):
        if self._ports_expanded:
            self.ports_content.grid_forget()
            self.btn_toggle_ports.configure(text="\u25B6  USB / COM порти")
            self._ports_expanded = False
        else:
            self.ports_content.grid(row=2, column=0, padx=10, pady=(0, 0), sticky="ew")
            self.btn_toggle_ports.configure(text="\u25BC  USB / COM порти")
            self._ports_expanded = True
            self._refresh_ports()
        self._fit_height()

    def _toggle_net(self):
        if self._net_expanded:
            self.net_content.grid_forget()
            self.btn_toggle_net.configure(text="\u25B6  Мережа")
            self._net_expanded = False
        else:
            self.net_content.grid(row=4, column=0, padx=10, pady=(0, 0), sticky="ew")
            self.btn_toggle_net.configure(text="\u25BC  Мережа")
            self._net_expanded = True
            self._refresh_network()
        self._fit_height()

    def _load_data(self):
        try:
            self.config_data = load_config()
        except Exception as e:
            self.config_data = {}
            self.lbl_client_id.configure(text=f"Помилка: {e}")
            return

        self.lbl_client_id.configure(text=self.config_data.get("client_id", "—"))
        self.lbl_phone.configure(text=self.config_data.get("support_phone", "—"))

        tg_link = self.config_data.get("telegram_link", "")
        if tg_link:
            qr_img = generate_qr(tg_link, size=140)
            self._qr_image = ctk.CTkImage(light_image=qr_img, dark_image=qr_img, size=(140, 140))
            self.lbl_qr.configure(image=self._qr_image, text="")

        self._refresh_ports()
        self._refresh_network()

    def _refresh_ports(self):
        self.ports_text.configure(state="normal")
        self.ports_text.delete("1.0", "end")

        def fetch():
            serial_ports = get_serial_ports()
            usb_devices = get_usb_devices()
            self.after(0, lambda: self._display_ports(serial_ports, usb_devices))

        threading.Thread(target=fetch, daemon=True).start()

    def _display_ports(self, serial_ports, usb_devices):
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

    def _refresh_network(self):
        self.lbl_local_ip.configure(text="...")
        self.lbl_netbird.configure(text="...")
        self.lbl_radmin.configure(text="...")

        def fetch():
            local_ip = get_local_ip()
            netbird_ip = get_netbird_ip()
            radmin_ip = get_radmin_ip()
            self.after(0, lambda: self._display_network(local_ip, netbird_ip, radmin_ip))

        threading.Thread(target=fetch, daemon=True).start()

    def _display_network(self, local_ip, netbird_ip, radmin_ip):
        self.lbl_local_ip.configure(text=local_ip)
        self.lbl_netbird.configure(text=netbird_ip)
        self.lbl_radmin.configure(text=radmin_ip)
