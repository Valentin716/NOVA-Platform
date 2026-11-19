import json
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response

app = FastAPI(title="Panel de Monitoreo Remoto")

agentes_conectados: dict[str, WebSocket] = {}
paneles_admin: list[WebSocket] = []
logs_servidor: list[str] = []


def registrar_log(mensaje: str) -> str:
    timestamp = datetime.now().strftime("%H:%M:%S")
    entrada = f"[{timestamp}] {mensaje}"
    logs_servidor.append(entrada)
    if len(logs_servidor) > 50:
        logs_servidor.pop(0)
    return entrada


@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    with open("server/static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)


@app.websocket("/ws/agente/{pc_id}")
async def websocket_agente(websocket: WebSocket, pc_id: str):
    await websocket.accept()
    agentes_conectados[pc_id] = websocket
    log = registrar_log(f"PC conectada: {pc_id}")
    await notificar_admins({"tipo": "log", "mensaje": log})
    await notificar_admins({"tipo": "estado_pcs", "pcs": list(agentes_conectados.keys())})

    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            payload["pc_id"] = pc_id
            await notificar_admins(payload)
    except WebSocketDisconnect:
        agentes_conectados.pop(pc_id, None)
        log = registrar_log(f"PC desconectada: {pc_id}")
        await notificar_admins({"tipo": "log", "mensaje": log})
        await notificar_admins({"tipo": "estado_pcs", "pcs": list(agentes_conectados.keys())})


@app.websocket("/ws/admin")
async def websocket_admin(websocket: WebSocket):
    await websocket.accept()
    paneles_admin.append(websocket)
    await websocket.send_json({
        "tipo": "init",
        "pcs": list(agentes_conectados.keys()),
        "logs": logs_servidor,
    })

    try:
        while True:
            data = await websocket.receive_text()
            orden = json.loads(data)
            pc_destino = orden.get("pc_id")
            accion = orden.get("accion")

            log = registrar_log(f"Orden '{accion}' enviada a {pc_destino}")
            await notificar_admins({"tipo": "log", "mensaje": log})

            if pc_destino in agentes_conectados:
                await agentes_conectados[pc_destino].send_text(json.dumps(orden))
    except WebSocketDisconnect:
        if websocket in paneles_admin:
            paneles_admin.remove(websocket)


async def notificar_admins(mensaje: dict):
    desconectados = []
    for admin in paneles_admin:
        try:
            await admin.send_json(mensaje)
        except Exception:
            desconectados.append(admin)
    for admin in desconectados:
        if admin in paneles_admin:
            paneles_admin.remove(admin)