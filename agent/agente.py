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

try:
    import cv2
    HAS_CAMERA = True
except ImportError:
    HAS_CAMERA = False

try:
    import numpy as np
    import sounddevice as sd
    HAS_AUDIO = True
except ImportError:
    HAS_AUDIO = False

CAMARA_ACTIVA = False


def construir_uri_agente(base_url: str, pc_id: str) -> str:
    url = base_url.strip().rstrip("/")
    if url.startswith("https://"):
        url = "wss://" + url[len("https://"):]
    elif url.startswith("http://"):
        url = "ws://" + url[len("http://"):]

    if "/ws/agente/" in url:
        url = url.split("/ws/agente/")[0]

    return f"{url}/ws/agente/{pc_id}"


def mostrar_chat_emergente(mensaje: str, pc_id: str):
    if not HAS_TK:
        print(f"\n[CHAT ADMIN -> {pc_id}]: {mensaje}\n")
        return
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo(f"Mensaje del Administrador - {pc_id}", mensaje)
        root.destroy()
    except Exception:
        print(f"\n[CHAT ADMIN -> {pc_id}]: {mensaje}\n")


def reproducir_audio(datos: dict, pc_id: str):
    frecuencia = float(datos.get("frecuencia", 880))
    duracion = float(datos.get("duracion", 0.6))
    texto = datos.get("texto", "").strip()

    if texto:
        print(f"[AUDIO / AVISO -> {pc_id}]: {texto}")

    if HAS_AUDIO:
        try:
            fs = 44100
            t = np.linspace(0, duracion, int(fs * duracion), endpoint=False)
            onda = 0.25 * np.sin(2 * np.pi * frecuencia * t)
            sd.play(onda, samplerate=fs)
            sd.wait()
            print(f"[AUDIO] Tono reproducido ({frecuencia} Hz) en {pc_id}.")
            return
        except Exception as e:
            print(f"[AUDIO] Error con sounddevice: {e}")

    os_name = platform.system()
    try:
        if os_name == "Windows":
            import winsound
            winsound.Beep(int(frecuencia), int(duracion * 1000))
        elif os_name == "Linux":
            if subprocess.run(["which", "paplay"], capture_output=True).returncode == 0:
                subprocess.Popen(["paplay", "/usr/share/sounds/freedesktop/stereo/bell.oga"])
            else:
                print("\a", end="", flush=True)
        else:
            print("\a", end="", flush=True)
    except Exception as e:
        print(f"[AUDIO] No se pudo reproducir audio en {pc_id}: {e}")


def ejecutar_comando_sistema(accion: str, datos: dict, pc_id: str):
    global CAMARA_ACTIVA
    os_name = platform.system()

    if accion == "apagar":
        try:
            if os_name == "Windows":
                res = subprocess.run(["shutdown", "/s", "/t", "0"], capture_output=True, text=True)
            else:
                res = subprocess.run(["systemctl", "poweroff"], capture_output=True, text=True)
                if res.returncode != 0:
                    res = subprocess.run(["poweroff"], capture_output=True, text=True)

            if res.returncode != 0:
                print(f"[APAGAR] Falló en {pc_id}: {res.stderr.strip() or 'revisa permisos de administrador/sudo'}")
        except Exception as e:
            print(f"[APAGAR] Error ejecutando apagado en {pc_id}: {e}")

    elif accion == "prender_camara" or accion == "camara":
        if "estado" in datos:
            CAMARA_ACTIVA = bool(datos.get("estado"))
        else:
            CAMARA_ACTIVA = not CAMARA_ACTIVA
        print(f"[CÁMARA] {'Activada' if CAMARA_ACTIVA else 'Desactivada'} en {pc_id} (HAS_CAMERA={HAS_CAMERA}).")

    elif accion == "apagar_camara":
        CAMARA_ACTIVA = False
        print(f"[CÁMARA] Desactivada en {pc_id}.")

    elif accion == "prender_audio" or accion == "audio":
        reproducir_audio(datos, pc_id)

    elif accion == "bloquear_input":
        if os_name == "Windows":
            try:
                import ctypes
                ctypes.windll.user32.BlockInput(True)
            except Exception as e:
                print(f"[INPUT] Error al bloquear en Windows: {e}")
        else:
            print("[INPUT] bloquear_input disponible principalmente en Windows.")

    elif accion == "desbloquear_input":
        if os_name == "Windows":
            try:
                import ctypes
                ctypes.windll.user32.BlockInput(False)
            except Exception as e:
                print(f"[INPUT] Error al desbloquear en Windows: {e}")

    elif accion == "bloquear_web":
        dominio = datos.get("dominio", "").strip()
        if dominio:
            hosts_path = r"C:\Windows\System32\drivers\etc\hosts" if os_name == "Windows" else "/etc/hosts"
            try:
                with open(hosts_path, "a", encoding="utf-8") as f:
                    f.write(f"\n127.0.0.1 {dominio}\n")
                print(f"[WEB] Dominio bloqueado en hosts: {dominio}")
            except PermissionError:
                print(f"[WEB] Sin permisos para editar {hosts_path}. Ejecuta como administrador/root.")
            except Exception as e:
                print(f"[WEB] Error al modificar hosts: {e}")

    elif accion == "denegar_ping":
        try:
            if os_name == "Windows":
                subprocess.run(
                    ["netsh", "advfirewall", "firewall", "add", "rule", "name=BlockICMP", "protocol=ICMPv4", "dir=in", "action=block"],
                    capture_output=True,
                )
            elif os_name == "Linux":
                subprocess.run(["sysctl", "-w", "net.ipv4.icmp_echo_ignore_all=1"], capture_output=True)
        except Exception as e:
            print(f"[PING] Error al denegar ping: {e}")

    elif accion == "permitir_ping":
        try:
            if os_name == "Windows":
                subprocess.run(
                    ["netsh", "advfirewall", "firewall", "delete", "rule", "name=BlockICMP"],
                    capture_output=True,
                )
            elif os_name == "Linux":
                subprocess.run(["sysctl", "-w", "net.ipv4.icmp_echo_ignore_all=0"], capture_output=True)
        except Exception as e:
            print(f"[PING] Error al permitir ping: {e}")


async def enviar_pantalla(websocket, pc_id: str):
    if not HAS_SCREEN:
        return
    try:
        with mss.MSS() as sct:
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
                    "pc_id": pc_id,
                    "imagen": img_str,
                }))
                await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[PANTALLA] Envío detenido en {pc_id}: {e}")


async def enviar_camara(websocket, pc_id: str):
    if not HAS_CAMERA:
        return
    cap = None
    try:
        while True:
            if CAMARA_ACTIVA:
                if cap is None or not cap.isOpened():
                    cap = cv2.VideoCapture(0)
                if cap and cap.isOpened():
                    ret, frame = cap.read()
                    if ret:
                        frame = cv2.resize(frame, (640, 360))
                        ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 60])
                        if ok:
                            img_str = base64.b64encode(encoded.tobytes()).decode("utf-8")
                            await websocket.send(json.dumps({
                                "tipo": "camara",
                                "pc_id": pc_id,
                                "imagen": img_str,
                            }))
                await asyncio.sleep(0.25)
            else:
                if cap is not None and cap.isOpened():
                    cap.release()
                    cap = None
                await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"[CÁMARA] Error en stream de {pc_id}: {e}")
    finally:
        if cap is not None and cap.isOpened():
            cap.release()


async def conectar_agente(pc_id: str, server_url: str):
    uri = construir_uri_agente(server_url, pc_id)
    while True:
        tasks = []
        try:
            async with websockets.connect(uri, ping_interval=20, ping_timeout=20) as websocket:
                print(f"Conectado exitosamente a {uri} como {pc_id}")
                tasks.append(asyncio.create_task(enviar_pantalla(websocket, pc_id)))
                if HAS_CAMERA:
                    tasks.append(asyncio.create_task(enviar_camara(websocket, pc_id)))

                async for message in websocket:
                    data = json.loads(message)
                    accion = data.get("accion")

                    if accion == "chat":
                        loop = asyncio.get_running_loop()
                        loop.run_in_executor(None, mostrar_chat_emergente, data.get("mensaje", ""), pc_id)
                    else:
                        loop = asyncio.get_running_loop()
                        loop.run_in_executor(None, ejecutar_comando_sistema, accion, data, pc_id)

        except Exception as e:
            print(f"No se pudo conectar a {uri} ({e}). Reintentando en 5 segundos...")
            await asyncio.sleep(5)
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        PC_ID = sys.argv[1]
    if len(sys.argv) > 2:
        SERVER_URL = sys.argv[2]

    print(f"Iniciando agente {PC_ID} hacia {construir_uri_agente(SERVER_URL, PC_ID)}...")
    asyncio.run(conectar_agente(PC_ID, SERVER_URL))