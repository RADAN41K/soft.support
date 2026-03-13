import platform
import socket
import subprocess

# Hide console window on Windows
_SUBPROCESS_KWARGS = {}
if platform.system() == "Windows":
    _SUBPROCESS_KWARGS["creationflags"] = (
        subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW")
        else 0x08000000
    )


def get_local_ip():
    """Get local IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "Не определён"


def get_netbird_ip():
    """Get NetBird VPN IP address."""
    try:
        out = subprocess.check_output(
            ["netbird", "status"], text=True, timeout=10,
            **_SUBPROCESS_KWARGS
        )
        for line in out.splitlines():
            if "NetBird IP" in line:
                parts = line.split(":")
                if len(parts) >= 2:
                    val = parts[-1].strip()
                    if val in ("N/A", "", "-"):
                        return "Не подключён"
                    ip = val.split("/")[0]
                    if ip and ip[0].isdigit():
                        return ip
        return "Не подключён"
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return "Не установлен"


def get_radmin_ip():
    """Get Radmin VPN IP address."""
    system = platform.system()
    try:
        if system == "Windows":
            out = subprocess.check_output(
                ["ipconfig"], text=True, timeout=10,
                **_SUBPROCESS_KWARGS
            )
            lines = out.splitlines()
            in_radmin = False
            for line in lines:
                if "Radmin" in line:
                    in_radmin = True
                if in_radmin and "IPv4" in line:
                    return line.split(":")[-1].strip()
                if in_radmin and line.strip() == "":
                    in_radmin = False

        elif system == "Darwin" or system == "Linux":
            out = subprocess.check_output(
                ["ifconfig"] if system == "Darwin" else ["ip", "addr"],
                text=True, timeout=10, **_SUBPROCESS_KWARGS
            )
            lines = out.splitlines()
            in_radmin = False
            for line in lines:
                if "radmin" in line.lower() or "rvpn" in line.lower():
                    in_radmin = True
                if in_radmin and "inet " in line:
                    parts = line.strip().split()
                    idx = parts.index("inet") + 1 if "inet" in parts else -1
                    if idx > 0 and idx < len(parts):
                        return parts[idx].split("/")[0]
                if in_radmin and line and not line.startswith((" ", "\t")):
                    in_radmin = False

        return "Не подключён"
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return "Не установлен"
