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
  la carpeta compilada a HostGator por **FTPS con `lftp`** (cifrado y con el certificado verificado).
  Solo se suben los archivos que cambiaron. `index.html` se sube al final y después se borran los
  `.js`/`.css` de versiones anteriores; los demás archivos de la carpeta no se tocan.

El backend tiene su propio workflow (`backend.yml`), que solo ejecuta pruebas y no se despliega.

### Configuración (una sola vez)

El panel se publica en **<https://consultas.uets.edu.ec/>** (raíz del subdominio, así que
`FRONTEND_BASE_HREF` se deja en `/`).

1. **HostGator:** ese subdominio abre la carpeta `public_html/website_9a02b4bd` de la cuenta.
   Lo más seguro es crear en cPanel → Cuentas FTP una cuenta limitada a esa carpeta (y poner
   `FTP_SERVER_DIR` = `./`), así el despliegue no puede tocar el resto del sitio. Con la cuenta FTP
   principal no hace falta configurar la carpeta.
2. **GitHub → repositorio → Settings → Secrets and variables → Actions:**

   | Tipo | Nombre | Valor |
   | --- | --- | --- |
   | Secret | `FTP_SERVER` | **Nombre del servidor** de HostGator, `gatorNNNN.hostgator.com` (cPanel → Información general → Nombre del servidor). No use `uets.edu.ec` ni `ftp.uets.edu.ec`: el certificado del FTP es `*.hostgator.com` y la conexión se rechaza |
   | Secret | `FTP_USERNAME` | Usuario de la cuenta FTP |
   | Secret | `FTP_PASSWORD` | Contraseña de la cuenta FTP |
   | Variable (opcional) | `FTP_SERVER_DIR` | Carpeta de destino **vista desde la cuenta FTP**, terminada en `/`. Por defecto `public_html/website_9a02b4bd/` (la carpeta del panel en HostGator, vista desde la cuenta FTP principal). Si usa una cuenta FTP limitada a esa carpeta, ponga `./` |
   | Variable | `API_URL` | Dirección **HTTPS** del servidor Python (p. ej. `https://api-bingo.midominio.com`) |
   | Variable (opcional) | `FRONTEND_BASE_HREF` | `/` por defecto (correcto para `consultas.uets.edu.ec`); solo cambia si el panel se mueve a una subcarpeta, p. ej. `/bingo/` |
   | Variable (opcional) | `GOOGLE_CLIENT_ID` | Solo si cambia el cliente de Google (por defecto, el de `public/env.js`) |
   | Variable (opcional) | `FTP_PORT` | Por defecto `21` |

   Las contraseñas van en **Secrets**: GitHub las oculta en los registros y nadie puede leerlas
   después de guardarlas.
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
y suba el contenido de esa carpeta, incluido `.htaccess`, con el Administrador de archivos de cPanel.

## Rutas

| Ruta | Quién |
| --- | --- |
| `/login` | Todos (botón de Google; registro de estudiantes la primera vez) |
| `/consulta?cedula=` | Público (`/buscar` redirige aquí) |
| `/mis-tablas` | Estudiantes |
| `/admin/users`, `/admin/add-user`, `/admin/user/:id/cartones`, `/admin/user/:id/add-carton` | Admin y animadores |
| `/admin/cartones`, `/admin/cartones/:id`, `/admin/buscar-participante` | Admin y animadores |
| `/admin/mi-curso` | Animadores (alumnos de su paralelo) |
| `/admin/reportes`, `/admin/animadores`, `/admin/estudiantes` | Solo admin |

## Estructura
- `src/app/core/`: configuración, sesión (`localStorage`), interceptor HTTP (URL base, token,
  cierre de sesión ante 401), guards por rol, carga de Google, utilidades de tablas y PDF.
- `src/app/shared/`: cuadrícula de tablas con descarga PDF y formulario modal de los CRUD.
- `src/app/layout/`: encabezado y menú del panel.
- `src/app/pages/`: una pantalla por ruta (componentes standalone con signals; carga diferida).
