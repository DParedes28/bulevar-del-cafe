# Bulevar del Café

Sitio público para consultar el borrador del Manual de Convivencia y enviar observaciones, más un panel privado para administrar el periodo, el PDF y los comentarios.

## Qué hace

- La página pública muestra el PDF cuando hay uno publicado y el formulario solo si existe una fecha límite que todavía no se cumple. La hora de referencia es `America/Bogota`.
- Sin fecha configurada, el formulario permanece abierto. Al guardar una fecha de cierre, se oculta cuando esa fecha se cumple.
- Cada observación guarda número de casa, nombre, cédula, página, artículo y el texto. El estado inicial es `nueva`.
- Eliminar una observación marca `deleted_at`. El listado y la exportación las ocultan, y el panel puede mostrarlas para restaurarlas.
- El PDF vive en Neon, así que el sitio y el panel leen el mismo archivo aunque sean dos servicios distintos.

## Variables de entorno

Copia `.env.example` a `.env` en la raíz del proyecto.

- `DATABASE_URL`: cadena directa de Neon, con un host que no incluya `-pooler`, y `sslmode=require`.
- `ADMIN_PASSWORD`: contraseña del panel. Solo la necesita Streamlit.

## Ejecución local

Desde la raíz del proyecto:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Edita `.env` y luego:

```powershell
uvicorn web.main:app --reload
streamlit run admin/streamlit_app.py
```

El sitio queda en `http://127.0.0.1:8000` y el panel en el puerto que indique Streamlit. Al arrancar, cualquiera de las dos aplicaciones crea las tablas si todavía no existen.

En el panel, el primer paso es guardar la fecha de cierre y publicar el PDF.

## Despliegue en Render

`render.yaml` define dos servicios web sobre este mismo repositorio:

- `bulevar-del-cafe` ejecuta FastAPI y solo necesita `DATABASE_URL`.
- `bulevar-del-cafe-admin` ejecuta Streamlit y necesita `DATABASE_URL` y `ADMIN_PASSWORD`.

Usa la cadena directa de Neon en ambos. El panel queda protegido por la contraseña; la dirección sigue siendo pública.
