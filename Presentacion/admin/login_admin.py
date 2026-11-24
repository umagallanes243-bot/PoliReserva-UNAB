"""La ruta histórica de administradores abre el acceso institucional."""

from fastapi.responses import RedirectResponse
from nicegui import app


@app.get('/admin-login')
def pagina_admin_login():
    return RedirectResponse('/login', status_code=303, headers={'Cache-Control': 'no-store'})
