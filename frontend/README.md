# Panel web del Bingo UETS (Angular)

Panel para vender tablas, administrar animadores y estudiantes, ver reportes, y la consulta pública de
tablas por cédula. Reemplaza al panel React (`gestor-usrs-bingo`) con las mismas pantallas y rutas.
Consume la API del servidor Python (carpeta `backend/` de este repo). El manual completo está en
[`backend/docs/MANUAL.md`](../backend/docs/MANUAL.md).

## Requisitos
- Node.js 20.19+ (Angular 21)
- Servidor Python encendido (por defecto en el puerto 5000)

## Uso

```powershell
npm install
npm start          # http://localhost:3000
npm run build      # genera dist/gestor-usrs-bingo-angular/browser
npx serve -s dist/gestor-usrs-bingo-angular/browser -l 3000
```

## Configuración (`public/env.js`)
Se lee al cargar la página, así que se puede editar después de compilar
(`dist/.../browser/env.js`) sin volver a construir.

| Campo | Qué es |
| --- | --- |
| `API_URL` | Dirección del servidor Python. Vacío = mismo equipo que abre el panel, puerto 5000. |
| `GOOGLE_CLIENT_ID` | ID de cliente OAuth de Google; debe coincidir con `GOOGLE_CLIENT_ID` del backend. |

La dirección desde la que se abre el panel (p. ej. `http://localhost:3000`) debe estar en
*Orígenes autorizados de JavaScript* del cliente OAuth en Google Cloud Console.

## Rutas

| Ruta | Quién |
| --- | --- |
| `/login` | Todos (botón de Google; registro de estudiantes la primera vez) |
| `/consulta?cedula=` | Público (`/buscar` redirige aquí) |
| `/mis-tablas` | Estudiantes |
| `/admin/users`, `/admin/add-user`, `/admin/user/:id/cartones`, `/admin/user/:id/add-carton` | Admin y animadores |
| `/admin/cartones`, `/admin/cartones/:id`, `/admin/buscar-participante` | Admin y animadores |
| `/admin/reportes`, `/admin/animadores`, `/admin/estudiantes` | Solo admin |

## Estructura
- `src/app/core/`: configuración, sesión (`localStorage`), interceptor HTTP (URL base, token,
  cierre de sesión ante 401), guards por rol, carga de Google, utilidades de tablas y PDF.
- `src/app/shared/`: cuadrícula de tablas con descarga PDF y formulario modal de los CRUD.
- `src/app/layout/`: encabezado y menú del panel.
- `src/app/pages/`: una pantalla por ruta (componentes standalone con signals; carga diferida).
