import asyncio
import base64
from io import BytesIO
import json
import os
import platform
import subprocess
import sys
import websockets

SERVER_URL = os.getenv("MONITOR_SERVER_URL", "wss://nova-platform-id56.onrender.com")
PC_ID = os.getenv("MONITOR_PC_ID", "PC-1")

try:
    import tkinter as tk
    from tkinter import messagebox
    HAS_TK = True
except Exception:
    HAS_TK = False

try:
    import mss
    from PIL import Image
    HAS_SCREEN = True
except ImportError:
    HAS_SCREEN = False


def construir_uri_agente(base_url: str, pc_id: str) -> str:
    url = base_url.strip().rstrip("/")
    if url.startswith("https://"):
        url = "wss://" + url[len("https://"):]
    elif url.startswith("http://"):
        url = "ws://" + url[len("http://"):]

    if "/ws/agente/" in url:
        url = url.split("/ws/agente/")[0]

    return f"{url}/ws/agente/{pc_id}"


def mostrar_chat_emergente(mensaje: str):
    if not HAS_TK:
        print(f"\n[CHAT ADMIN -> {PC_ID}]: {mensaje}\n")
        return
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(f"Mensaje del Administrador - {PC_ID}", mensaje)
        root.destroy()
    except Exception:
        print(f"\n[CHAT ADMIN -> {PC_ID}]: {mensaje}\n")


def ejecutar_comando_sistema(accion: str, datos: dict):
    os_name = platform.system()

    if accion == "apagar":
        if os_name == "Windows":
            os.system("shutdown /s /t 0")
        else:
            os.system("poweroff")

    elif accion == "bloquear_input":
        if os_name == "Windows":
            import ctypes
            ctypes.windll.user32.BlockInput(True)
        else:
            print("bloquear_input: disponible principalmente en Windows con API de usuario.")

    elif accion == "desbloquear_input":
        if os_name == "Windows":
            import ctypes
            ctypes.windll.user32.BlockInput(False)

    elif accion == "bloquear_web":
        dominio = datos.get("dominio", "").strip()
        if dominio:
            hosts_path = r"C:\Windows\System32\drivers\etc\hosts" if os_name == "Windows" else "/etc/hosts"
            try:
                with open(hosts_path, "a", encoding="utf-8") as f:
                    f.write(f"\n127.0.0.1 {dominio}\n")
                print(f"Dominio bloqueado en hosts: {dominio}")
            except PermissionError:
                print(f"Sin permisos para editar {hosts_path}. Ejecuta como administrador/root.")
            except Exception as e:
                print(f"Error al modificar hosts: {e}")

    elif accion == "denegar_ping":
        if os_name == "Windows":
            subprocess.run(
                ["netsh", "advfirewall", "firewall", "add", "rule", "name=BlockICMP", "protocol=ICMPv4", "dir=in", "action=block"],
                capture_output=True,
            )
        elif os_name == "Linux":
            subprocess.run(["sysctl", "-w", "net.ipv4.icmp_echo_ignore_all=1"], capture_output=True)

    elif accion == "permitir_ping":
        if os_name == "Windows":
            subprocess.run(
                ["netsh", "advfirewall", "firewall", "delete", "rule", "name=BlockICMP"],
                capture_output=True,
            )
        elif os_name == "Linux":
            subprocess.run(["sysctl", "-w", "net.ipv4.icmp_echo_ignore_all=0"], capture_output=True)


async def enviar_pantalla(websocket):
    if not HAS_SCREEN:
        return
    try:
        with mss.mss() as sct:
            monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
            while True:
                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
                img.thumbnail((800, 450))
                buffer = BytesIO()
                img.save(buffer, format="JPEG", quality=60)
                img_str = base64.b64encode(buffer.getvalue()).decode("utf-8")

                await websocket.send(json.dumps({
                    "tipo": "pantalla",
                    "imagen": img_str,
                }))
                await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    except Exception:
        pass


async def conectar_agente():
    uri = construir_uri_agente(SERVER_URL, PC_ID)
    while True:
        task_screen = None
        try:
            async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as websocket:
                print(f"Conectado exitosamente a {uri} como {PC_ID}")
                task_screen = asyncio.create_task(enviar_pantalla(websocket))

                async for message in websocket:
                    data = json.loads(message)
                    accion = data.get("accion")

                    if accion == "chat":
                        loop = asyncio.get_running_loop()
                        loop.run_in_executor(None, mostrar_chat_emergente, data.get("mensaje", ""))
                    else:
                        ejecutar_comando_sistema(accion, data)

        except Exception as e:
            print(f"No se pudo conectar a {uri} ({e}). Reintentando en 5 segundos...")
            await asyncio.sleep(5)
        finally:
            if task_screen and not task_screen.done():
                task_screen.cancel()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        PC_ID = sys.argv[1]
    if len(sys.argv) > 2:
        SERVER_URL = sys.argv[2]

    print(f"Iniciando agente {PC_ID} hacia {construir_uri_agente(SERVER_URL, PC_ID)}...")
    asyncio.run(conectar_agente())