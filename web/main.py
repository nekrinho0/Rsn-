import io
import asyncio
import hashlib
import json
import os
import time
import zipfile
from datetime import date, datetime
from pathlib import Path
from uuid import UUID

import httpx
from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile, Query
from fastapi.responses import FileResponse, StreamingResponse
from openpyxl import load_workbook
from pydantic import BaseModel, Field

app = FastAPI(title='Rosen Excel')
ROOT = Path(__file__).parent
stock_listeners: set[asyncio.Queue] = set()


def notify_stock_updated():
    for queue in tuple(stock_listeners):
        if queue.empty():
            queue.put_nowait('updated')


@app.get('/api/stock-eventos')
async def stock_events():
    async def events():
        queue = asyncio.Queue(maxsize=1)
        stock_listeners.add(queue)
        try:
            yield ': connected\n\n'
            # Renueva periódicamente la conexión para no bloquear el apagado.
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                try:
                    await asyncio.wait_for(queue.get(), timeout=min(15, max(0.1, deadline - time.monotonic())))
                    yield 'event: stock-updated\ndata: {}\n\n'
                except asyncio.TimeoutError:
                    yield ': heartbeat\n\n'
        finally:
            stock_listeners.discard(queue)
    return StreamingResponse(events(), media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


def config():
    url = os.environ.get('SUPABASE_URL', '').rstrip('/')
    key = os.environ.get('SUPABASE_PUBLISHABLE_KEY', '')
    if not url.startswith('https://') or not key:
        raise HTTPException(503, 'Falta configurar Supabase en el servidor.')
    return url, key


async def request(method, path, token=None, **kwargs):
    url, key = config()
    headers = {'apikey': key}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(method, url + path, headers=headers, **kwargs)
    except httpx.RequestError:
        raise HTTPException(502, 'No se pudo conectar con Supabase.')
    if response.is_error:
        status = response.status_code
        raise HTTPException(status if status in (400, 401, 403) else 502,
                            'Credenciales o permisos inválidos.' if status in (400, 401, 403)
                            else 'Supabase no pudo completar la operación.')
    return response.json() if response.content else None


async def session(authorization: str = Header(default='')):
    if not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Inicia sesión para continuar.')
    token = authorization[7:]
    await request('GET', '/auth/v1/user', token)
    return token


class Login(BaseModel):
    email: str
    password: str


class DeleteInventory(BaseModel):
    confirmar: bool = False


@app.delete('/api/excel-actual')
async def delete_current_excel(body: DeleteInventory, token=Depends(session)):
    profile = await request('GET', '/rest/v1/perfiles?select=rol', token)
    if not profile or profile[0]['rol'] != 'administrador':
        raise HTTPException(403, 'Solo el administrador puede eliminar el inventario.')
    if not body.confirmar:
        raise HTTPException(400, 'Debes confirmar la eliminación del inventario actual.')
    await request('DELETE', '/rest/v1/excel_actual?id=eq.1', token)
    notify_stock_updated()
    return {'mensaje': 'El inventario actual fue eliminado.'}


@app.post('/api/login')
async def login(body: Login):
    result = await request('POST', '/auth/v1/token?grant_type=password', json=body.model_dump())
    return {key: result[key] for key in ('access_token', 'refresh_token', 'expires_in')}


class RefreshSession(BaseModel):
    refresh_token: str


@app.post('/api/refresh')
async def refresh_session(body: RefreshSession):
    result = await request('POST', '/auth/v1/token?grant_type=refresh_token',
                           json=body.model_dump())
    return {key: result[key] for key in ('access_token', 'refresh_token', 'expires_in')}


@app.get('/api/stock')
async def stock(token=Depends(session)):
    data = await request('GET', '/rest/v1/excel_actual?id=eq.1&select=nombre,columnas,filas,fecha', token)
    return data[0] if data else None


@app.get('/api/me')
async def my_profile(token=Depends(session)):
    profiles = await request('GET', '/rest/v1/perfiles?select=rol', token)
    if not profiles or profiles[0]['rol'] not in ('administrador', 'visualizador'):
        raise HTTPException(403, 'Tu usuario todavía no tiene acceso asignado.')
    return {'rol': profiles[0]['rol']}


@app.get('/api/stock-vendedores')
async def seller_stock():
    # Consulta de solo lectura sin cuenta: el nombre del navegador no es autenticación.
    data = await request('GET', '/rest/v1/excel_actual?id=eq.1&select=nombre,columnas,filas,fecha')
    return data[0] if data else None


@app.get('/api/administrativo')
async def administrative_stock(token=Depends(session)):
    profile = await request('GET', '/rest/v1/perfiles?select=rol', token)
    if not profile or profile[0]['rol'] != 'administrador':
        raise HTTPException(403, 'Esta sección es exclusiva del administrador.')
    return await stock(token)


@app.get('/api/historial')
async def update_history(offset: int = Query(default=0, ge=0), token=Depends(session)):
    profile = await request('GET', '/rest/v1/perfiles?select=rol', token)
    if not profile or profile[0]['rol'] != 'administrador':
        raise HTTPException(403, 'Solo el administrador puede consultar el historial.')
    rows = await request('GET', '/rest/v1/historial_actualizaciones'
                         '?select=id,fecha,email,nombre_archivo,cantidad_filas'
                         f'&order=fecha.desc,id.desc&limit=26&offset={offset}', token)
    return {'registros': rows[:25], 'hay_mas': len(rows) > 25}


class Activity(BaseModel):
    visita: UUID
    dispositivo: UUID
    nombre: str = Field(default='', max_length=80)
    apellido: str = Field(default='', max_length=100)
    activo: bool = True


@app.post('/api/actividad')
async def register_activity(body: Activity, authorization: str = Header(default='')):
    token = None
    if authorization:
        token = await session(authorization)
    elif not body.nombre.strip() or not body.apellido.strip():
        raise HTTPException(400, 'Ingresa nombre y apellido.')
    await request('POST', '/rest/v1/rpc/registrar_actividad', token, json={
        'p_visita': str(body.visita), 'p_dispositivo': str(body.dispositivo),
        'p_nombre': body.nombre, 'p_apellido': body.apellido, 'p_activo': body.activo,
    })
    return {'ok': True}


@app.get('/api/actividad')
async def read_activity(offset: int = Query(default=0, ge=0), token=Depends(session)):
    profile = await request('GET', '/rest/v1/perfiles?select=rol', token)
    if not profile or profile[0]['rol'] != 'administrador':
        raise HTTPException(403, 'Solo administradores pueden consultar los accesos.')
    result = await request('POST', '/rest/v1/rpc/consultar_actividad', token,
                           json={'p_offset': offset})
    return {**result, 'accesos': result['accesos'][:25], 'hay_mas': len(result['accesos']) > 25}


@app.get('/api/actividad/historial')
async def person_access_history(nombre: str = Query(min_length=1, max_length=320),
                                tipo: str = Query(min_length=1, max_length=30),
                                offset: int = Query(default=0, ge=0), token=Depends(session)):
    profile = await request('GET', '/rest/v1/perfiles?select=rol', token)
    if not profile or profile[0]['rol'] != 'administrador':
        raise HTTPException(403, 'Solo administradores pueden consultar los accesos.')
    rows = await request('GET', '/rest/v1/registro_accesos', token, params={
        'select': 'entrada,ultima_actividad', 'nombre': f'eq.{nombre}', 'tipo': f'eq.{tipo}',
        'order': 'entrada.desc,id.desc', 'limit': 26, 'offset': offset,
    })
    return {'accesos': rows[:25], 'hay_mas': len(rows) > 25}


def parse_excel(content):
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if sum(item.file_size for item in archive.infolist()) > 50 * 1024 * 1024:
                raise ValueError('El Excel descomprimido supera 50 MB.')
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=False)
        try:
            sheet = workbook.worksheets[0]
            if sheet.max_column and sheet.max_column > 100:
                raise ValueError('Máximo 100 columnas.')
            iterator = sheet.iter_rows()
            first = next(iterator, None)
            if not first:
                raise ValueError('El archivo está vacío.')
            columns = [str(cell.value).strip() if cell.value is not None else '' for cell in first]
            if not all(columns) or len(set(columns)) != len(columns):
                raise ValueError('La primera fila debe contener encabezados únicos y no vacíos.')
            rows = []
            for row in iterator:
                values = []
                for cell in row:
                    value = cell.value
                    if cell.data_type == 'f':
                        raise ValueError('El archivo contiene fórmulas. Guarda una copia con solo valores.')
                    if isinstance(value, (date, datetime)):
                        value = value.isoformat()
                    elif isinstance(value, int) and cell.number_format and set(cell.number_format) == {'0'}:
                        value = str(value).zfill(len(cell.number_format))
                    values.append(value)
                if any(value is not None for value in values):
                    rows.append(values)
                if len(rows) > 10000:
                    raise ValueError('Máximo 10.000 filas por archivo.')
            if not rows:
                raise ValueError('El Excel no contiene datos.')
            if len(json.dumps(rows, ensure_ascii=False)) > 8_000_000:
                raise ValueError('El contenido del Excel es demasiado grande.')
            return columns, rows
        finally:
            workbook.close()
    except ValueError:
        raise
    except Exception:
        raise ValueError('No se pudo leer el archivo. Selecciona un Excel .xlsx válido.')


async def read_admin_excel(file, token):
    # RLS también verifica el administrador al guardar.
    profile = await request('GET', '/rest/v1/perfiles?select=rol', token)
    if not profile or profile[0]['rol'] != 'administrador':
        raise HTTPException(403, 'Solo el administrador puede subir archivos.')
    if not (file.filename or '').lower().endswith('.xlsx'):
        raise HTTPException(400, 'Selecciona un archivo .xlsx.')
    content = await file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, 'El archivo supera 5 MB.')
    from starlette.concurrency import run_in_threadpool
    try:
        columns, rows = await run_in_threadpool(parse_excel, content)
    except ValueError as error:
        raise HTTPException(400, str(error))
    return content, columns, rows


@app.post('/api/preview')
async def preview(file: UploadFile = File(...), token=Depends(session)):
    content, columns, rows = await read_admin_excel(file, token)
    return {'nombre': file.filename, 'columnas': columns, 'filas': rows[:10],
            'cantidad': len(rows), 'sha256': hashlib.sha256(content).hexdigest()}


@app.post('/api/upload')
async def upload(file: UploadFile = File(...), token=Depends(session),
                 x_preview_sha256: str = Header(default='')):
    content, columns, rows = await read_admin_excel(file, token)
    if hashlib.sha256(content).hexdigest() != x_preview_sha256:
        raise HTTPException(400, 'Revisa la vista previa de este archivo antes de publicarlo.')
    await request('POST', '/rest/v1/rpc/guardar_excel', token,
                  json={'p_nombre': file.filename, 'p_columnas': columns, 'p_filas': rows})
    notify_stock_updated()
    return {'cantidad': len(rows)}


@app.get('/app.js')
async def javascript():
    return FileResponse(ROOT / 'app.js', media_type='text/javascript')


@app.get('/')
@app.get('/subir')
@app.get('/inventario')
@app.get('/administrativo')
async def page():
    return FileResponse(ROOT / 'index.html')
