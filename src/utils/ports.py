import platform
import re
import subprocess

import serial
import serial.tools.list_ports

from src.utils.logging import log
from src.utils.platform_utils import SUBPROCESS_KWARGS as _SUBPROCESS_KWARGS


def _check_port_status(device):
    """Check COM port status: 'busy', 'ready', or 'empty'.

    busy  — port is in use by another program (device connected & working)
    ready — port can be opened and has data (device found but not in use)
    empty — port can be opened but no data (nothing connected)
    """
    try:
        ser = serial.Serial(device, baudrate=9600, timeout=0.3)
        try:
            data = ser.read(64)
            if data:
                return "ready"
            return "empty"
        finally:
            ser.close()
    except serial.SerialException as e:
        err_msg = str(e).lower()
        # "Access is denied" / "PermissionError" = another program holds the port
        if "access" in err_msg or "permission" in err_msg or "in use" in err_msg:
            return "busy"
        # Other errors (device removed, port doesn't exist)
        return "disconnected"


_prev_com_status = {}


def get_serial_ports():
    """Get list of physical COM/serial ports with connection status."""
    global _prev_com_status
    ports = []
    for port in serial.tools.list_ports.comports():
        lower = f"{port.device} {port.description}".lower()
        if any(kw in lower for kw in INTERNAL_SERIAL_KEYWORDS):
            continue

        status = _check_port_status(port.device)

        # Log only on first scan or status change
        prev = _prev_com_status.get(port.device)
        if prev != status:
            log(f"COM {port.device}: {status} | {port.description} | {port.hwid}")
            _prev_com_status[port.device] = status

        ports.append({
            "device": port.device,
            "description": port.description,
            "hwid": port.hwid,
            "status": status,
        })
    return ports


INTERNAL_SERIAL_KEYWORDS = [
    "debug-console", "bluetooth", "wlan", "internal",
    "built-in", "btusb", "bthusb",
]

INTERNAL_USB_KEYWORDS = [
    "hub", "host controller", "root hub", "usb bus", "hsic",
    "internal", "built-in", "bluetooth", "bthusb", "btusb",
    "isp", "xhci", "ehci", "ohci", "uhci", "chipset",
    "smbus", "thunderbolt", "pci", "controller",
    "apple t2", "apple internal", "fingerprint",
    "ir receiver", "ambient light", "facetime",
    "generic hub", "usb3.0 hub", "usb2.0 hub",
]


def _is_external(name: str) -> bool:
    """Filter out internal USB controllers/hubs, keep external devices."""
    lower = name.lower()
    return not any(kw in lower for kw in INTERNAL_USB_KEYWORDS)


def get_usb_devices():
    """Get list of external USB devices based on OS."""
    system = platform.system()
    devices = []

    try:
        if system == "Darwin":
            out = subprocess.check_output(
                ["system_profiler", "SPUSBDataType", "-detailLevel", "mini"],
                text=True, timeout=10, **_SUBPROCESS_KWARGS
            )
            current_device = None
            is_internal = False
            for line in out.splitlines():
                stripped = line.strip()
                indent = len(line) - len(line.lstrip())
                # Top-level entries (Bus, Host Controller) at indent <= 4
                # Device names at indent 8-12, ending with ":"
                if stripped.endswith(":") and not stripped.startswith("Host Controller"):
                    name = stripped.rstrip(":")
                    if indent <= 4:
                        # USB Bus header — skip
                        current_device = None
                        is_internal = False
                    else:
                        # Save previous device if external
                        if current_device and not is_internal:
                            if _is_external(current_device):
                                devices.append(current_device)
                        current_device = name
                        is_internal = False
                elif current_device:
                    if "Built-In" in stripped:
                        is_internal = True
                    elif "Location ID:" in stripped:
                        if "built" in stripped.lower() or "internal" in stripped.lower():
                            is_internal = True
            # Last device
            if current_device and not is_internal:
                if _is_external(current_device):
                    devices.append(current_device)

        elif system == "Linux":
            out = subprocess.check_output(
                ["lsusb"], text=True, timeout=10, **_SUBPROCESS_KWARGS
            )
            for line in out.splitlines():
                if line.strip():
                    parts = line.split("ID ")
                    if len(parts) > 1:
                        vid_pid_name = parts[1]
                        vid_pid = vid_pid_name.split(" ", 1)[0]
                        name = vid_pid_name.split(" ", 1)[1] if " " in vid_pid_name else vid_pid
                        # Skip 1d6b:xxxx (Linux Foundation root hubs)
                        if vid_pid.startswith("1d6b:"):
                            continue
                        if _is_external(name):
                            devices.append(name.strip())

        elif system == "Windows":
            # Port USB detection from PS script logic:
            # 1. Find devices with USB\VID_ or USBSTOR\ InstanceId
            # 2. Filter by allowed classes, exclude internal
            # 3. Determine physical port number via LocationPaths
            ps_script = r"""
$allowed = @('HIDClass','Printer','Image','WPD','DiskDrive','CDROM','Ports','SmartCardReader','Media','Net')
$exclude = 'Hub|Root|Controller|Composite|Bluetooth|Fingerprint|Internal|Integrated|IR |Biometric'
$devs = Get-PnpDevice -Status OK -EA SilentlyContinue |
  Where-Object {
    ($_.InstanceId -match '^USB\\VID_' -or $_.InstanceId -match '^USBSTOR\\') -and
    $_.Class -in $allowed -and
    $_.FriendlyName -notmatch $exclude
  }
foreach ($d in $devs) {
  # Check if device is physically present
  $present = try { (Get-PnpDeviceProperty -InstanceId $d.InstanceId -KeyName 'DEVPKEY_Device_IsPresent' -EA SilentlyContinue).Data } catch { $true }
  if (-not $present) { continue }
  $id2 = $d.InstanceId
  if ($id2 -match '^USBSTOR') {
    $par = try { (Get-PnpDeviceProperty -InstanceId $id2 -KeyName 'DEVPKEY_Device_Parent' -EA SilentlyContinue).Data } catch { $null }
    if ($par) { $id2 = $par }
  }
  $paths = try { (Get-PnpDeviceProperty -InstanceId $id2 -KeyName 'DEVPKEY_Device_LocationPaths' -EA SilentlyContinue).Data } catch { $null }
  $pn = $null
  if ($paths) {
    $p = if ($paths -is [array]) { $paths[0] } else { [string]$paths }
    $mm = [regex]::Matches($p,'USB\((\d+)\)')
    if ($mm.Count -gt 0) { $pn = [int]$mm[$mm.Count-1].Groups[1].Value }
  }
  if (-not $pn) {
    $loc = $d.LocationInformation
    if ($loc -match 'Port_#(\d+)') { $pn = [int]$Matches[1] }
    elseif ($loc -match '\.(\d+)$') { $pn = [int]$Matches[1] }
  }
  if ($pn -and $pn -gt 0) { "$($d.FriendlyName) [USB$pn]" }
}
"""
            out = subprocess.check_output(
                ["powershell", "-NoProfile", "-Command", ps_script],
                text=True, timeout=15, **_SUBPROCESS_KWARGS
            )
            seen = set()
            for line in out.splitlines():
                name = line.strip()
                if name and name not in seen:
                    seen.add(name)
                    devices.append(name)
            devices.sort(key=lambda x: int(re.sub(r'\D', '', x) or 0))

    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return devices
