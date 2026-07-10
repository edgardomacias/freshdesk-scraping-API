# Exportador de Tickets Freshdesk

Script en Python que descarga todos los tickets (incidentes) de una cuenta de **Freshdesk** vía su API REST, los limpia y enriquece con datos legibles (nombre de agente, nombre de grupo, tiempo de seguimiento), y genera un reporte en Excel.

## ¿Qué problema resuelve?

Freshdesk expone los tickets vía API con IDs numéricos para agentes, grupos y campos personalizados, y con el detalle del incidente en HTML. Este script automatiza:

- La paginación completa de tickets (sin límite manual de fechas ni estados).
- La resolución de `responder_id` → nombre de agente y `group_id` → nombre de grupo.
- La limpieza de HTML en la descripción del ticket.
- El cálculo del tiempo total de seguimiento (time tracking) por ticket.
- La exportación de todo a un único archivo `.xlsx` listo para análisis.

## Requisitos

- Python 3.8+
- Dependencias:
  ```bash
  pip install requests pandas openpyxl
  ```
- Una API Key de Freshdesk (se obtiene desde el perfil del agente en Freshdesk).

## Configuración

El script lee la API Key desde una variable de entorno:

```bash
# PowerShell
$env:FRESHDESK_KEY = "tu_api_key"

# Bash
export FRESHDESK_KEY="tu_api_key"
```

Otros parámetros están definidos como constantes al inicio de [exportar_ticket.py](exportar_ticket.py):

| Constante | Descripción |
|---|---|
| `DOMAIN` / `BASE_URL` | Subdominio de Freshdesk (`ummia.freshdesk.com`) |
| `PER_PAGE` | Tickets por página (máx. 100 según la API) |
| `MAX_PAGINAS` | Límite de páginas a recorrer (300 → hasta 30.000 tickets) |
| `PAUSA_SEGUNDOS` | Pausa entre requests para no exceder el rate limit |
| `INCLUIR_TIEMPO_SEGUIMIENTO` | Si es `True`, hace una llamada extra por ticket para sumar el tiempo registrado (más lento) |

> La autenticación de Freshdesk usa Basic Auth con la API Key como usuario y cualquier valor como contraseña (`PASSWORD = "x"` es un placeholder requerido por la API, no una credencial real).

## Cómo funciona el script

### 1. `get_agentes()` y `get_grupos()`
Descargan, paginando de 100 en 100, el catálogo completo de agentes y grupos de la cuenta, y devuelven diccionarios `{id: nombre}` para poder traducir los IDs numéricos que trae cada ticket.

### 2. `get_tiempo_seguimiento(ticket_id)`
Consulta el endpoint `tickets/{id}/time_entries` y suma `time_spent_in_seconds` de todas las entradas, devolviendo el total en minutos. Incluye:
- Reintentos con backoff ante errores de conexión.
- Manejo del código `429` (rate limit) respetando el header `Retry-After`.

### 3. `limpiar_html(texto)`
Elimina cualquier etiqueta HTML de la descripción del ticket usando una expresión regular, dejando solo texto plano.

### 4. `descargar_y_limpiar_tickets()`
Función principal, orquesta todo el proceso:

1. Carga los catálogos de agentes y grupos.
2. Pagina sobre `GET /api/v2/tickets` usando `updated_since=2010-01-01` para forzar que la API devuelva tickets de **todos los estados** (abiertos, resueltos, cerrados, etc.), no solo los activos.
3. Maneja el rate limit (`429`) reintentando tras el tiempo indicado por Freshdesk.
4. Para cada ticket descargado, construye una fila con:
   - Datos básicos: ID, asunto, tipo, estado, prioridad, fecha de creación.
   - Agente y grupo resueltos a nombre (vía los catálogos del paso 1).
   - Tiempo total de seguimiento (si `INCLUIR_TIEMPO_SEGUIMIENTO` está activo).
   - Etiquetas (tags), datos del solicitante (nombre, correo).
   - Campos personalizados `cf_producto` y `cf_otra_descripcion` (dependen de la configuración de tu cuenta Freshdesk; si aparecen vacíos, revisa el nombre real del campo en `custom_fields` de la respuesta de la API).
   - Descripción del incidente, ya limpia de HTML.
5. Vuelca todo en un `DataFrame` de pandas y lo exporta a Excel en:
   ```
   G:\Unidades compartidas\Área de Tecnología\Respaldo_Ticket\reporte_detallado_incidentes.xlsx
   ```

### 5. Punto de entrada
```python
if __name__ == "__main__":
    descargar_y_limpiar_tickets()
```
Al ejecutar `python exportar_ticket.py`, se dispara todo el proceso descrito arriba.

## Ejecución

```bash
python exportar_ticket.py
```

La consola mostrará el progreso: carga de catálogos, páginas de tickets descargadas, avance del cálculo de tiempos de seguimiento (cada 50 tickets), y finalmente la ruta del archivo Excel generado.

## Notas y limitaciones

- El script está acoplado al dominio `tudominio.freshdesk.com` y a una ruta de red compartida (`G:\...`) como destino del reporte; para reutilizarlo en otra cuenta u organización hay que ajustar `DOMAIN`, `BASE_URL` y `directorio_destino`.
- Con `INCLUIR_TIEMPO_SEGUIMIENTO = True` el proceso es notablemente más lento, ya que se hace una llamada adicional a la API por cada ticket.
- El límite de `MAX_PAGINAS = 300` junto a `PER_PAGE = 100` cubre hasta 30.000 tickets; cuentas con más tickets requerirán aumentar este valor.
