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

## CI/CD y despliegue en HostGator

El workflow [`.github/workflows/frontend.yml`](../.github/workflows/frontend.yml) se ejecuta cuando
cambia algo en `frontend/`:

- **CI** (también en pull requests): `npm ci`, revisión de formato con Prettier y compilación.
- **CD** (solo al llegar a `main`, o a mano con *Run workflow*): genera `env.js` de producción y sube
  la carpeta compilada a HostGator por **FTP** con FTP-Deploy-Action, igual que
  `sistema-solicitudes-migration-Front` (`academico.uets.edu.ec`). Solo se suben los archivos que
  cambiaron y se borran los que ya no existen en el compilado.
- **Protección:** antes de subir revisa la carpeta de destino. Si ya contiene otro sitio (un
  `index.html` sin el archivo `bingo-panel.txt` del panel), se detiene sin subir nada.

> Se usa FTP sin cifrar porque FTPS falla en el canal de datos del FTP de HostGator
> ("tlsv1 alert decode error"). El usuario y la contraseña FTP viajan sin cifrar: use una cuenta FTP
> exclusiva para el panel, limitada a su carpeta.

El backend tiene su propio workflow (`backend.yml`), que solo ejecuta pruebas y no se despliega.

### Configuración (una sola vez)

El panel se publica en **<https://consultas.uets.edu.ec/>** (raíz del subdominio, así que
`FRONTEND_BASE_HREF` se deja en `/`).

1. **HostGator (cPanel → Cuentas FTP):** cree una cuenta FTP **exclusiva del panel** cuyo directorio
   sea `public_html/website_9a02b4bd` (la carpeta de `consultas.uets.edu.ec`). **No reutilice** la
   cuenta FTP de `academico.uets.edu.ec`: entra en otra carpeta y el panel se subiría encima de ese
   sitio (la protección lo detecta y detiene el despliegue).
2. **GitHub → repositorio → Settings → Secrets and variables → Actions:**

   | Tipo | Nombre | Valor |
   | --- | --- | --- |
   | Secret | `FTP_SERVER` | Servidor FTP, p. ej. `uets.edu.ec` (solo el nombre, sin `ftp://`) |
   | Secret | `FTP_USERNAME` | Usuario de la cuenta FTP del panel (p. ej. `consultas@uets.edu.ec`) |
   | Secret | `FTP_PASSWORD` | Contraseña de esa cuenta FTP |
   | Variable (opcional) | `FTP_SERVER_DIR` | Carpeta de destino dentro de la cuenta FTP, terminada en `/`. Por defecto `./` (la cuenta entra directamente en la carpeta del panel) |
   | Variable (opcional) | `FRONTEND_BASE_HREF` | `/` por defecto (correcto para `consultas.uets.edu.ec`); solo cambia si el panel se mueve a una subcarpeta, p. ej. `/bingo/` |
   | Variable (opcional) | `GOOGLE_CLIENT_ID` | Solo si cambia el cliente de Google (por defecto, el de `public/env.js`) |

   Las contraseñas van en **Secrets**: GitHub las oculta en los registros y nadie puede leerlas
   después de guardarlas.

   La dirección del servidor Python (`API_URL`, hoy `https://bingo.190-15-143-91.nip.io`) está
   fija en `.github/workflows/frontend.yml`, job `deploy`. Si el backend cambia de dirección, se
   cambia ahí y se hace push.
3. **Servidor Python:** en su `.env`, ponga `CORS_ORIGINS=https://consultas.uets.edu.ec` (separe con
   comas si el panel también se abre desde otra dirección, p. ej. `http://localhost:3000`) y
   reinicie el servidor.
4. **Google Cloud Console:** agregue `https://consultas.uets.edu.ec` en *Orígenes autorizados de
   JavaScript* (sin barra al final).

El despliegue usa el *environment* `hostgator` de GitHub. Si quiere aprobar cada despliegue a mano,
active *Required reviewers* en Settings → Environments → hostgator.

> **HTTPS:** HostGator sirve el panel con HTTPS, así que el navegador solo le permite hablar con un API
> en HTTPS. `http://IP:5000` no funcionará desde ahí. Publique el servidor Python con Cloudflare
> Tunnel (ver el manual, sección 7.2).

El archivo `public/.htaccess` (va dentro del compilado) hace que las rutas del panel funcionen al
recargar la página en Apache y evita que el navegador guarde en caché `index.html` y `env.js`.

**Despliegue manual** (sin GitHub): `npm run build`, edite `dist/gestor-usrs-bingo-angular/browser/env.js`
y suba el contenido de esa carpeta, incluidos `.htaccess` y `bingo-panel.txt`, con el Administrador de archivos de cPanel.

## Rutas

| Ruta | Quién |
| --- | --- |
| `/login` | Todos (botón de Google; registro de estudiantes la primera vez) |
| `/consulta?cedula=` | Público (`/buscar` redirige aquí) |
| `/mis-tablas` | Estudiantes |
| `/admin/users`, `/admin/add-user`, `/admin/user/:id/cartones`, `/admin/user/:id/add-carton` | Admin y animadores |
| `/admin/cartones`, `/admin/cartones/:id`, `/admin/buscar-participante` | Admin y animadores |
| `/admin/mi-curso` | Animadores (alumnos de su paralelo) |
| `/admin/reportes`, `/admin/animadores`, `/admin/estudiantes`, `/admin/mantenimiento` | Solo admin |

## Estructura
- `src/app/core/`: configuración, sesión (`localStorage`), interceptor HTTP (URL base, token,
  cierre de sesión ante 401), guards por rol, carga de Google, utilidades de tablas y PDF.
- `src/app/shared/`: cuadrícula de tablas con descarga PDF y formulario modal de los CRUD.
- `src/app/layout/`: encabezado y menú del panel.
- `src/app/pages/`: una pantalla por ruta (componentes standalone con signals; carga diferida).
