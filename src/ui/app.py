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
        self.geometry("520x750")
        self.minsize(480, 650)
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

        self._build_ui()
        self._load_data()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)

        # --- Block 1: Client / Branding ---
        self.client_frame = ctk.CTkFrame(self, fg_color=self.ORANGE, corner_radius=10)
        self.client_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")
        self.client_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.client_frame, text="Технiчна пiдтримка LimanSoft",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=self.WHITE).grid(
            row=0, column=0, padx=10, pady=(12, 2), sticky="w")

        ctk.CTkLabel(self.client_frame, text="Скануйте QR-код LimanSoft Help 24/7",
                     font=ctk.CTkFont(size=13),
                     text_color=self.WHITE).grid(
            row=1, column=0, padx=10, pady=(0, 5), sticky="w")

        # QR + info side by side
        self.info_frame = ctk.CTkFrame(self.client_frame, fg_color="transparent")
        self.info_frame.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="ew")
        self.info_frame.grid_columnconfigure(1, weight=1)

        self.lbl_qr = ctk.CTkLabel(self.info_frame, text="",
                                    fg_color=self.WHITE, corner_radius=8)
        self.lbl_qr.grid(row=0, column=0, rowspan=3, padx=(0, 15), pady=5, sticky="nw")

        self.lbl_client_id = ctk.CTkLabel(self.info_frame, text="—",
                                           font=ctk.CTkFont(size=14, weight="bold"),
                                           text_color=self.WHITE)
        self.lbl_client_id.grid(row=0, column=1, pady=(5, 2), sticky="w")

        self.lbl_phone = ctk.CTkLabel(self.info_frame, text="—",
                                       font=ctk.CTkFont(size=14),
                                       text_color=self.WHITE)
        self.lbl_phone.grid(row=1, column=1, pady=2, sticky="w")

        # --- Block 2: Ports ---
        self.ports_frame = ctk.CTkFrame(self, fg_color=self.WHITE, border_width=1,
                                         border_color="#E0E0E0", corner_radius=10)
        self.ports_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        self.ports_frame.grid_columnconfigure(0, weight=1)

        header_ports = ctk.CTkFrame(self.ports_frame, fg_color="transparent")
        header_ports.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")
        header_ports.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header_ports, text="USB / COM порти",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=self.TEXT_DARK).grid(
            row=0, column=0, sticky="w")

        self.btn_refresh_ports = ctk.CTkButton(
            header_ports, text="Оновити", width=90,
            fg_color=self.ORANGE, hover_color=self.DARK_ORANGE,
            command=self._refresh_ports)
        self.btn_refresh_ports.grid(row=0, column=1, sticky="e")

        self.ports_text = ctk.CTkTextbox(self.ports_frame, height=120)
        self.ports_text.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")

        # --- Block 3: Network ---
        self.net_frame = ctk.CTkFrame(self, fg_color=self.WHITE, border_width=1,
                                       border_color="#E0E0E0", corner_radius=10)
        self.net_frame.grid(row=2, column=0, padx=10, pady=(5, 10), sticky="ew")
        self.net_frame.grid_columnconfigure(1, weight=1)

        header_net = ctk.CTkFrame(self.net_frame, fg_color="transparent")
        header_net.grid(row=0, column=0, columnspan=2, padx=10, pady=(10, 5), sticky="ew")
        header_net.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(header_net, text="Мережа",
                     font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=self.TEXT_DARK).grid(
            row=0, column=0, sticky="w")

        self.btn_refresh_net = ctk.CTkButton(
            header_net, text="Оновити", width=90,
            fg_color=self.ORANGE, hover_color=self.DARK_ORANGE,
            command=self._refresh_network)
        self.btn_refresh_net.grid(row=0, column=1, sticky="e")

        ctk.CTkLabel(self.net_frame, text="Локальний IP:",
                     text_color=self.TEXT_DARK).grid(
            row=1, column=0, padx=10, pady=2, sticky="w")
        self.lbl_local_ip = ctk.CTkLabel(self.net_frame, text="...",
                                          text_color=self.TEXT_DARK)
        self.lbl_local_ip.grid(row=1, column=1, padx=10, pady=2, sticky="w")

        ctk.CTkLabel(self.net_frame, text="NetBird IP:",
                     text_color=self.TEXT_DARK).grid(
            row=2, column=0, padx=10, pady=2, sticky="w")
        self.lbl_netbird = ctk.CTkLabel(self.net_frame, text="...",
                                         text_color=self.TEXT_DARK)
        self.lbl_netbird.grid(row=2, column=1, padx=10, pady=2, sticky="w")

        ctk.CTkLabel(self.net_frame, text="Radmin IP:",
                     text_color=self.TEXT_DARK).grid(
            row=3, column=0, padx=10, pady=(2, 10), sticky="w")
        self.lbl_radmin = ctk.CTkLabel(self.net_frame, text="...",
                                        text_color=self.TEXT_DARK)
        self.lbl_radmin.grid(row=3, column=1, padx=10, pady=(2, 10), sticky="w")

    def _load_data(self):
        try:
            self.config_data = load_config()
        except Exception as e:
            self.config_data = {}
            self.lbl_client_id.configure(text=f"Ошибка: {e}")
            return

        self.lbl_client_id.configure(text=self.config_data.get("client_id", "—"))
        self.lbl_phone.configure(text=self.config_data.get("support_phone", "—"))

        tg_link = self.config_data.get("telegram_link", "")
        if tg_link:
            qr_img = generate_qr(tg_link, size=180)
            self._qr_image = ctk.CTkImage(light_image=qr_img, dark_image=qr_img, size=(180, 180))
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
