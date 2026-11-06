# Web simplificada: subir y consultar Excel

En Administrativo, pulsa un nombre o correo de Actividad por navegador para abrir su historial de entradas en una ventana con paginación. Se filtra por nombre/correo exacto y tipo; vendedores con el mismo nombre declarado comparten la lista, ya que no tienen identidad autenticada. No requiere cambios SQL adicionales.

## Registro de conexiones y entradas

Ejecuta `web/registro_accesos.sql` en Supabase SQL Editor. Crea la tabla persistente `registro_accesos` y funciones para registrar actividad y consultar accesos. No elimina entradas automáticamente. El historial de Excel permanece por separado en `historial_actualizaciones`, sin borrarse al reemplazar o eliminar el inventario.

Cada apertura, navegación o recarga con identidad asignada crea una entrada; las señales cada 30 segundos actualizan su última actividad, sin crear una fila por señal. La página oculta avisa inactividad; si el teléfono desaparece, el estado conectado caduca a los 90 segundos. Los administradores ven los últimos 100 navegadores y todas las entradas paginadas de 25 en 25. El panel consulta automáticamente cada 30 segundos mientras esté visible.

Los administradores se identifican mediante su sesión validada y correo obtenido de Supabase. El nombre de vendedores es declarado y no verifica identidad. El dispositivo es un identificador aleatorio del navegador, no del hardware: otros navegadores o borrar datos crean otro identificador. No se registra ubicación ni IP. Cerrar una pestaña puede no enviar el aviso, por eso el estado se estima mediante el plazo de actividad.

Si la base está inaccesible, aparece un aviso; no se impide consultar stock ni se garantiza recuperar las entradas que no pudieron registrarse. Reinicia el servidor y recarga los dispositivos una vez después de instalar esta actualización.

## Historial administrativo

Ejecuta `web/historial_actualizaciones.sql` en Supabase SQL Editor para activar el historial. El trigger registra cada inserción o actualización del inventario en la misma transacción: fecha, correo obtenido de auth.users, nombre del archivo y cantidad de filas. No permite escritura del historial desde el navegador ni lectura para vendedores. Los registros anteriores a su activación no se pueden reconstruir. Las eliminaciones no borran el historial ni crean una entrada de publicación.

Administrativo muestra las entradas más recientes primero, en páginas de 25 y con hora de America/Santiago. Se actualiza al recibir notificaciones de una nueva carga. Reinicia el servidor y recarga el navegador tras activar el SQL.

## Eliminar Excel actual

Ejecuta `web/permitir_eliminar_excel.sql` una vez en SQL Editor para habilitar DELETE bajo la política RLS de administradores ya existente. En Subir Excel, el botón Eliminar Excel actual solicita confirmación y elimina los datos publicados (no hay archivo original almacenado). Una eliminación correcta avisa a los otros dispositivos y deja la consulta vacía hasta publicar otro Excel. No elimina perfiles ni usuarios. La operación es irreversible; cancelar no envía ninguna solicitud.

## Actualizaciones en vivo

Cuando una carga termina correctamente, el servidor envía un evento SSE a los navegadores abiertos en Inventario o Administrativo. Estos consultan el inventario nuevo conservando la búsqueda y, cuando sea posible, la página actual. No se notifican cargas fallidas. Al reconectar o regresar a la pestaña también se consulta el estado actual.

No requiere SQL adicional. Reinicia el servidor y recarga los navegadores una vez para activar esta funcionalidad. Funciona con el servidor actual de un solo proceso: todos los dispositivos deben acceder al mismo servidor. Si se despliega con varios procesos o réplicas, será necesario sustituir la notificación en memoria por un servicio compartido o Supabase Realtime. Los cambios realizados directamente en la base no emiten este evento. Las pestañas suspendidas por el teléfono se actualizan al volver a abrirlas.

## Vendedores sin cuenta

Ejecuta `web/acceso_vendedores.sql` en Supabase SQL Editor para habilitar lectura sin autenticación. No vuelvas a ejecutar schema.sql. El permiso anónimo permite consultar el inventario a cualquiera con acceso al enlace o la API; el nombre y apellido no verifican identidad ni restringen la lectura a empleados. Las cargas, vista previa y datos administrativos siguen exigiendo sesión y rol administrador.

En `/inventario` se pide nombre y apellido una vez por navegador. Se guardan solo en localStorage, no se envían al servidor ni constituyen un registro de actividad. No hay un bot?n para cambiar el nombre: se conserva para las pr?ximas visitas desde ese navegador. En modo incógnito, al borrar datos del navegador o cambiar de dispositivo se pedirán nuevamente. Acceso administrador abre el formulario de correo y contraseña.

Reinicia el servidor y recarga con Ctrl+F5 después de actualizar.

Esta versión reemplaza el plan Flutter para el flujo solicitado. Abre la misma web desde computadores o teléfonos; los datos se guardan en Supabase, no en el navegador. La carpeta frontend anterior se conserva, pero no se usa aquí.

## Configuración pendiente

1. Instala Python 3.11 o posterior desde https://www.python.org/downloads/windows/ y habilita su incorporación al PATH.
2. Crea un proyecto Supabase. En SQL Editor ejecuta web/schema.sql **una sola vez**. Este esquema está destinado a un proyecto nuevo.
3. Crea usuarios desde Authentication y añade sus perfiles usando los ejemplos al final del SQL. El administrador sube archivos; los visualizadores consultan. Nadie se asigna roles desde la web.
4. En PowerShell, desde la raíz Rosen:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r web\requirements.txt
$env:SUPABASE_URL = 'https://TU-PROYECTO.supabase.co'
$env:SUPABASE_PUBLISHABLE_KEY = 'TU-CLAVE-PUBLICA'
.\.venv\Scripts\python.exe -m uvicorn web.main:app --host 0.0.0.0 --port 8000
```

Usa únicamente la clave pública publishable o anon; no hace falta service_role. No compartas contraseñas ni claves secretas en el chat.

Abre http://localhost:8000/subir e inicia sesión como administrador. Publica un .xlsx y abre http://localhost:8000/inventario. Desde otro dispositivo en la misma red abre http://IP-DEL-PC:8000/inventario, utilizando la IPv4 local que muestra ipconfig. El PC debe permanecer encendido y el firewall debe permitir el puerto para tu red privada.

Para acceder desde cualquier red queda pendiente alojar este servidor con HTTPS y configurar estas dos variables en el proveedor. No expongas el servidor HTTP directamente a internet. Esta implementación no se ha publicado todavía.

## Comportamiento

### Vista previa y filtros

En Subir Excel, selecciona el archivo y pulsa **Revisar Excel**. Se valida completo y se muestran las primeras diez filas, el tamaño, las columnas y el número total de registros. **Confirmar y publicar** guarda el mismo archivo revisado; cambiar de archivo descarta la vista previa. Revisar no escribe en Supabase.

En Inventario puedes combinar búsqueda con filtros de familia, negocio y disponibilidad. Familia y negocio se habilitan cuando existen esos encabezados. La columna Stock Disponible se reconoce ignorando mayúsculas y acentos; si no existe, selecciona la columna de stock manualmente. No se ha inspeccionado todavía el Excel original.

Los indicadores cuentan registros encontrados después de búsqueda, familia y negocio, antes del filtro de disponibilidad. Con stock significa mayor que cero; sin stock significa cero o negativo; stock bajo significa mayor que cero y menor o igual al umbral (5 por defecto). Vacíos y textos no numéricos no se consideran agotados. Números reales de Excel y enteros almacenados como texto se aceptan para filtrar; textos con separadores ambiguos se muestran como sin dato válido.

Después de estos cambios, reinicia uvicorn y recarga el navegador con Ctrl+F5. No necesitas modificar ni volver a ejecutar el SQL.

Pruebas del flujo de importación (sin conexión a Supabase):

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_web_upload.py -v
```

Se verificaron siete casos: vista previa sin escritura, conservación de ceros iniciales, publicación revisada, rechazo sin revisión coincidente, archivos inválidos, permisos de visualizador, fórmulas y límite de muestra. La interfaz y la integración con un Supabase real requieren comprobación manual.

Se importa la primera hoja, con encabezados únicos en su primera fila. Se conservan sus columnas, sin suponer el formato Rosen. Se rechazan fórmulas: exporta una copia con solo valores. Se preservan SKU de texto y números con formato simple de ceros iniciales. Máximo 5 MB, 100 columnas y 10.000 registros. Para formatos específicos necesitamos inspeccionar el Excel real.

Una publicación válida reemplaza atómicamente la hoja completa compartida; conserva el inventario anterior si falla. No guarda el archivo original ni historial. El usuario debe confirmar el reemplazo. La consulta tiene búsqueda y paginación de 50 filas; esta primera versión descarga el conjunto completo hasta el límite indicado.

La sesión dura hasta que vence el token de Supabase o se cierra la pestaña. Al vencer se requiere iniciar sesión de nuevo. Los permisos se verifican tanto en el servidor como mediante RLS.

## Verificación pendiente

El entorno Python .venv ya permite ejecutar las pruebas automatizadas. No se ha verificado automáticamente la interfaz en un navegador ni la integración contra un Supabase real. Antes de uso: comprobar la vista previa, filtros con el Excel real y consulta desde otro dispositivo.
