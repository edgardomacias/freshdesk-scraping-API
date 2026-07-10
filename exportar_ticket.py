import requests
import pandas as pd
import re
import time
import os

# --- CONFIGURACIÓN ---
API_KEY = os.getenv("FRESHDESK_KEY")      # Reemplaza con tu llave de Freshdesk
DOMAIN = "tudominio.freshdesk.com"        # Reemplaza con tu subdominio (ej: miempresa)
PASSWORD = "x"

# Freshdesk permite hasta 100 por página y hasta 300 páginas (30,000 tickets total

PER_PAGE = 100
MAX_PAGINAS = 300
# Pausa entre requests para respetar el rate limit de la API (varía según plan)
PAUSA_SEGUNDOS = 1
# Activar para obtener tiempo de seguimiento (hace una llamada extra por ticket, más lento)
INCLUIR_TIEMPO_SEGUIMIENTO = True

BASE_URL = f"https://tudomino.freshdesk.com/api/v2/tickets"

def get_agentes():
    """Descarga el listado de agentes y devuelve un dict {id: nombre}."""
    agentes = {}
    pagina = 1
    while True:
        url = f"https://tudominio.freshdesk.com/api/v2/agents?per_page=100&page={pagina}"
        resp = requests.get(url, auth=(API_KEY, PASSWORD), timeout=30)
        if resp.status_code != 200:
            break
        data = resp.json()
        if not data:
            break
        for a in data:
            agentes[a["id"]] = a.get("contact", {}).get("name", "")
        if len(data) < 100:
            break
        pagina += 1
        time.sleep(PAUSA_SEGUNDOS)
    print(f"  Agentes cargados: {len(agentes)}")
    return agentes


def get_grupos():
    """Descarga el listado de grupos y devuelve un dict {id: nombre}."""
    grupos = {}
    pagina = 1
    while True:
        url = f"https://tudominio.freshdesk.com/api/v2/groups?per_page=100&page={pagina}"
        resp = requests.get(url, auth=(API_KEY, PASSWORD), timeout=30)
        if resp.status_code != 200:
            break
        data = resp.json()
        if not data:
            break
        for g in data:
            grupos[g["id"]] = g.get("name", "")
        if len(data) < 100:
            break
        pagina += 1
        time.sleep(PAUSA_SEGUNDOS)
    print(f"  Grupos cargados: {len(grupos)}")
    return grupos


def get_tiempo_seguimiento(ticket_id, max_reintentos=3):
    """Obtiene el tiempo total de seguimiento (en minutos) de un ticket."""
    url = f"https://tudominio.freshdesk.com/api/v2/tickets/{ticket_id}/time_entries"
    intento = 0
    while True:
        try:
            resp = requests.get(url, auth=(API_KEY, PASSWORD), timeout=30)
        except requests.exceptions.RequestException as e:
            intento += 1
            if intento >= max_reintentos:
                print(f"  Error de conexión en ticket {ticket_id} tras {max_reintentos} intentos: {e}")
                return None
            print(f"  Error de conexión en ticket {ticket_id}, reintentando ({intento}/{max_reintentos})...")
            time.sleep(5 * intento)
            continue
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 60))
            time.sleep(retry_after)
            continue
        if resp.status_code != 200:
            return None
        entries = resp.json()
        total = sum(e.get("time_spent_in_seconds", 0) for e in entries)
        return round(total / 60, 2) if total else 0


def limpiar_html(texto):
    """Elimina etiquetas HTML y deja solo el texto plano."""
    if not texto:
        return ""
    limpio = re.compile('<.*?>')
    return re.sub(limpio, '', str(texto))

def descargar_y_limpiar_tickets():
    print("Conectando con Freshdesk para descargar incidentes...")

    print("Cargando catálogos de agentes y grupos...")
    agentes = get_agentes()
    grupos = get_grupos()

    todos_los_tickets = []
    pagina = 1

    # updated_since con fecha antigua fuerza la API a devolver tickets de TODOS los estados
    FECHA_INICIO = "2010-01-01T00:00:00Z"

    while pagina <= MAX_PAGINAS:
        url = f"{BASE_URL}?include=description,requester&per_page={PER_PAGE}&page={pagina}&updated_since={FECHA_INICIO}"
        response = requests.get(url, auth=(API_KEY, PASSWORD), timeout=30)

        # Rate limit alcanzado: Freshdesk devuelve 429
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            print(f"  Rate limit alcanzado. Esperando {retry_after}s antes de continuar...")
            time.sleep(retry_after)
            continue  # Reintentar la misma página

        if response.status_code != 200:
            print(f"Error en página {pagina}. Código: {response.status_code}")
            break

        tickets = response.json()

        if not tickets:
            break  # No hay más páginas

        todos_los_tickets.extend(tickets)
        print(f"  Página {pagina}: {len(tickets)} tickets descargados (total: {len(todos_los_tickets)})")

        if len(tickets) < PER_PAGE:
            break  # Última página (incompleta)

        pagina += 1
        time.sleep(PAUSA_SEGUNDOS)

    if not todos_los_tickets:
        print("No se obtuvieron tickets.")
        return

    # Procesar los datos
    # NOTA: Los nombres cf_* de campos personalizados dependen de tu cuenta.
    # Si Producto u Otra Descripción traen None, ajusta las claves revisando
    # la sección "custom_fields" de cualquier ticket en la API.
    total_tickets = len(todos_los_tickets)
    datos_limpios = []
    for i, t in enumerate(todos_los_tickets, 1):
        custom = t.get("custom_fields", {})
        requester = t.get("requester", {})
        ticket_id = t.get("id")

        if INCLUIR_TIEMPO_SEGUIMIENTO:
            if i % 50 == 0:
                print(f"  Obteniendo tiempo de seguimiento... {i}/{total_tickets}")
            tiempo = get_tiempo_seguimiento(ticket_id)
            time.sleep(PAUSA_SEGUNDOS)
        else:
            tiempo = None

        datos_limpios.append({
            "Ticket ID": ticket_id,
            "Asunto": t.get("subject"),
            "Tipo": t.get("type"),
            "Estado": t.get("status"),
            "Prioridad": t.get("priority"),
            "Fecha Creación": t.get("created_at"),
            "Agente": agentes.get(t.get("responder_id"), ""),
            "Grupo": grupos.get(t.get("group_id"), ""),
            "Tiempo Total Seguimiento (min)": tiempo,
            "Etiquetas": ", ".join(t.get("tags", [])),
            "Nombre": requester.get("name"),
            "Correo": requester.get("email"),
            "Producto": custom.get("cf_producto"),
            "Otra Descripción": custom.get("cf_otra_descripcion"),
            "Detalle del Incidente": limpiar_html(t.get("description", "")),
        })

    df = pd.DataFrame(datos_limpios)
    directorio_destino = r"G:\Unidades compartidas\Área de Tecnología\Respaldo_Ticket"
    os.makedirs(directorio_destino, exist_ok=True)
    nombre_archivo = os.path.join(directorio_destino, "reporte_detallado_incidentes.xlsx")
    df.to_excel(nombre_archivo, index=False)

    print(f"\n--- Proceso Finalizado ---")
    print(f"Tickets procesados: {len(datos_limpios)}")
    print(f"Archivo generado: {nombre_archivo}")

if __name__ == "__main__":
    descargar_y_limpiar_tickets()