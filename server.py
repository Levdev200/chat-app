import asyncio
import websockets
import json
import os
import psycopg2
import time
from http.server import SimpleHTTPRequestHandler, HTTPServer
import threading
from aiohttp import web


# --- CONFIGURACIÓN DE BASE DE DATOS ---
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "chat_dev")
DB_USER = os.getenv("DB_USER", "chatuser")
DB_PASSWORD = os.getenv("DB_PASSWORD", "supersecretpassword")

CONEXIONES = set()
DB_CONN = None


# --- FUNCIONES DE BASE DE DATOS ---
def get_db_connection():
    global DB_CONN
    if DB_CONN is None or DB_CONN.closed:
        DB_CONN = psycopg2.connect(
            host=DB_HOST, database=DB_NAME, user=DB_USER, password=DB_PASSWORD
        )
    return DB_CONN


def crear_tabla_mensajes():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mensajes (
            id SERIAL PRIMARY KEY,
            usuario VARCHAR(100) NOT NULL,
            contenido TEXT NOT NULL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    cur.close()


def guardar_mensaje(usuario, contenido):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO mensajes (usuario, contenido) VALUES (%s, %s);",
            (usuario, contenido),
        )
        conn.commit()
        cur.close()
    except Exception as e:
        print(f"Error al guardar mensaje: {e}")


# --- FUNCIONES WEBSOCKET ---

# --- FUNCIONES WEBSOCKET ---
async def notificar_usuarios(mensaje):
    """Envía un mensaje a todos los clientes conectados activos."""
    if not CONEXIONES:
        return

    desconectados = set()
    for ws in CONEXIONES:
        try:
            await ws.send(mensaje)
        except Exception:
            desconectados.add(ws)

    # Limpia los sockets cerrados o con error
    for ws in desconectados:
        CONEXIONES.remove(ws)


async def manejador_mensajes(websocket, path):
    """Maneja la conexión de cada cliente WebSocket."""
    print(f"Nuevo cliente conectado desde {websocket.remote_address}")
    CONEXIONES.add(websocket)

    try:
        async for mensaje_json in websocket:
            data = json.loads(mensaje_json)
            usuario = data.get("user", "Anónimo")
            texto = data.get("text", "")

            guardar_mensaje(usuario, texto)
            mensaje_completo = f"[{usuario}]: {texto}"
            print(f"Mensaje recibido: {mensaje_completo}")
            await notificar_usuarios(mensaje_completo)

    except websockets.exceptions.ConnectionClosed:
        print(f"Cliente desconectado: {websocket.remote_address}")
    finally:
        if websocket in CONEXIONES:
            CONEXIONES.remove(websocket)


# --- SERVIDOR HTTP ---
async def index(request):
    response = web.FileResponse("index.html")
    response.headers["Cache-Control"] = "no-store"
    response.headers["Connection"] = "keep-alive"
    return response



async def iniciar_servidor():
    # Configurar rutas HTTP
    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_static("/", ".", show_index=False)

    # Servidor WebSocket
    async def ws_handler(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        CONEXIONES.add(ws)
        print(f"Cliente conectado: {request.remote}")

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    usuario = data.get("user", "Anónimo")
                    texto = data.get("text", "")
                    guardar_mensaje(usuario, texto)
                    mensaje_completo = f"[{usuario}]: {texto}"
                    print(f"Mensaje recibido: {mensaje_completo}")
                    # Notificar a todos
                    for conn in list(CONEXIONES):
                        try:
                            await conn.send_str(mensaje_completo)
                        except:
                            CONEXIONES.remove(conn)
                elif msg.type == web.WSMsgType.ERROR:
                    print(f"Error en WS: {ws.exception()}")
        finally:
            if ws in CONEXIONES:
                CONEXIONES.remove(ws)
                print("Cliente desconectado")

        return ws

    app.router.add_get("/ws", ws_handler)

    # Iniciar el servidor
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", 80)
    print("Servidor HTTP+WebSocket ejecutándose en http://0.0.0.0:80")
    await site.start()

    while True:
        await asyncio.sleep(3600)  # Mantiene corriendo el servidor


if __name__ == "__main__":
    # Espera conexión a la base de datos
    MAX_RETRIES = 10
    RETRY_DELAY = 3

    for attempt in range(MAX_RETRIES):
        try:
            print(f"Intento de conexión a la DB: {attempt + 1}/{MAX_RETRIES}")
            crear_tabla_mensajes()
            print("Conexión a la DB exitosa.")
            break
        except Exception as e:
            print(f"Error de conexión: {e}")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
            else:
                print("No se pudo conectar a la DB.")
                exit(1)

    asyncio.run(iniciar_servidor())

