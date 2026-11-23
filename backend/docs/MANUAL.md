# Manual del Sistema de Bingo UETS

Este manual explica dónde está cada parte del sistema, cómo encenderlo, cómo se juega con el tablero,
cómo entra cada tipo de usuario y cómo publicarlo para que se use desde fuera del colegio.

---

## 1. Las tres piezas del sistema

| Pieza | Carpeta | Qué hace | Dirección |
| --- | --- | --- | --- |
| **Base de datos** (MongoDB) | Servicio de Windows "MongoDB" | Guarda tablas, participantes, estudiantes, animadores | `mongodb://localhost:27017`, base `bingo_db` |
| **Servidor del juego** (Python) | `bingo-system\backend` | Muestra el **tablero del bingo** y atiende la API del panel | `http://localhost:5000` |
| **Panel web** (Angular) | `bingo-system\frontend` | Login con Google, venta de tablas, animadores, estudiantes, reportes, consulta pública | `http://localhost:3000` |

Rutas completas: `C:\Users\USUARIO\Desktop\sistemas UETS\Desarrollos\...`

```
 Navegador ── Panel web (3000) ──┐
                                 ├──► Servidor Python (5000) ──► MongoDB (27017)
 Pantalla del juego ── Tablero ──┘
```

El **tablero** lo sirve el servidor Python y **solo lo puede abrir el administrador** (sección 4).

---

## 2. Instalación (solo la primera vez en una computadora)

### 2.1 Servidor Python
En PowerShell, dentro de `bingo-system\backend`:

```powershell
python -m venv env
env\Scripts\pip install -r requirements.txt
Copy-Item .env.example .env
```

Abra `.env` con el Bloc de notas y revise:

| Variable | Qué poner |
| --- | --- |
| `GOOGLE_CLIENT_ID` | Ya viene puesto (ID de cliente de Google del colegio). |
| `BINGO_SECRET_KEY` | Una clave larga y secreta. Genérela con `env\Scripts\python -c "import secrets; print(secrets.token_urlsafe(48))"` y péguela. **No la comparta.** |
| `BINGO_ADMIN_EMAILS` | `admin@uets.edu.ec` (separe con comas si hay más administradores). |
| `CORS_ORIGINS` | `*` en la red local; al publicar, la dirección del panel (ver sección 7). |

> El archivo `.env` tiene datos secretos: nunca lo suba a GitHub (ya está excluido).

### 2.2 Panel web
Requiere Node.js 20.19 o superior. En PowerShell, dentro de `bingo-system\frontend`:

```powershell
npm install
```

La dirección del servidor Python está en `public\env.js` (campo `API_URL`). Vacío (el valor por
defecto) significa "la misma computadora que abre el panel, puerto 5000", que sirve tanto en
`localhost` como por IP en la red. Solo cámbielo si el API está en otro equipo o dominio (sección 7).
Después de compilar, el archivo queda en `dist\gestor-usrs-bingo-angular\browser\env.js` y se puede
editar ahí **sin recompilar**.

### 2.3 Google Cloud Console (una sola vez)
En <https://console.cloud.google.com> → *APIs y servicios* → *Credenciales* → cliente OAuth
`579049993014-...apps.googleusercontent.com` → **Orígenes autorizados de JavaScript**: agregue cada
dirección desde la que se abre el panel, por ejemplo:

- `http://localhost:3000`
- la dirección pública del panel (p. ej. `https://bingo.uets.edu.ec`)

No hace falta configurar "URI de redireccionamiento". Si falta un origen, el botón de Google muestra
un error (`origin_mismatch`).

---

## 3. Encender el sistema (cada día de uso)

1. **MongoDB**: normalmente arranca solo con Windows. Para comprobarlo:
   `Get-Service MongoDB` debe decir `Running` (si no: `Start-Service MongoDB` como administrador).
2. **Servidor del juego**: en `bingo-system\backend`:
   ```powershell
   .\iniciar_servidor.ps1
   ```
   Si Windows bloquea el script: `powershell -ExecutionPolicy Bypass -File .\iniciar_servidor.ps1`

   Al arrancar muestra las direcciones correctas, por ejemplo:
   ```
   Abra el tablero en: http://localhost:5000/
   Abra el tablero en: http://192.168.200.72:5000/  (desde otras computadoras de la red)
   ```
   ⚠️ La línea `Serving on http://0.0.0.0:5000` **no** es una dirección para el navegador.
   Deje esta ventana abierta mientras dure el evento; para apagar, presione `Ctrl + C`.
3. **Panel web** (para vender tablas / administrar): en `bingo-system\frontend`:
   ```powershell
   npm start
   ```
   Se abre en `http://localhost:3000`. (Para publicarlo de forma estable, vea la sección 7.)

Comprobación rápida: `http://localhost:5000/health` debe responder `{"database":"ok","status":"ok"}`.

---

## 4. El tablero del bingo (jugar)

1. Abra el tablero **como administrador**, de una de estas dos formas:
   - En el panel, botón **Tablero** (arriba a la derecha): se abre en otra pestaña con la sesión ya
     iniciada.
   - O directamente **`http://localhost:5000/`** (o `http://<IP-del-servidor>:5000/`): pide
     **Acceder con Google** y solo deja pasar a los correos de `BINGO_ADMIN_EMAILS`. Para esto, agregue
     también `http://localhost:5000` en los orígenes de Google (sección 2.3).
2. Pulse **Empezar Juego** → se abre el **Tablero Maestro** (`/pages/masterTable.html`).
3. Cada vez que sale una bola:
   - **Clic** sobre el número → lo marca (se pinta oscuro).
   - **Doble clic** → lo desmarca (si se marcó por error).
4. A la derecha, **Progreso de Tablas** muestra las 3 tablas con más aciertos.
5. **Gana la tabla llena** (25 aciertos). Aparece como **(GANADOR)**, se guarda en la base y se genera su
   comprobante PDF en `backend\winners\ganador_<serial>.pdf`.
6. **Nuevo Juego** (en el tablero) reinicia la ronda: limpia las bolas y deja fuera las tablas que ya
   ganaron. **No borra nada.** Para empezar todo desde cero con tablas nuevas, vea la sección 5.6.

**¿Qué tablas juegan?** Solo las **asignadas a un participante** (vendidas) y que no han ganado. Si se
vendieron tablas después de abrir el tablero, pulse **Nuevo Juego** (o reinicie el servidor) para
incluirlas. Si el tablero no muestra tablas, todavía no hay ventas registradas.

**Acceso:** animadores, estudiantes o cualquier otra persona ven la pantalla de acceso y no pueden
jugar, marcar bolas ni reiniciar la partida. El botón **Salir** (esquina superior derecha) cierra la
sesión del tablero; la sesión también vence a las horas de `BINGO_SESSION_HOURS`.

---

## 5. Ingresar al panel (quién entra y cómo)

Todos entran en el panel con **"Iniciar sesión con Google"** usando su cuenta `@uets.edu.ec`.

| Quién | Cómo obtiene acceso | Qué ve |
| --- | --- | --- |
| **Administrador** | `admin@uets.edu.ec` (variable `BINGO_ADMIN_EMAILS`) | Todo: participantes, tablas, reportes, **Animadores**, **Estudiantes**, reservar tablas |
| **Animador** | El administrador le pone su correo en **Animadores** | Sus participantes, las tablas de su rango y **Mi curso** (los alumnos de su paralelo) |
| **Estudiante** | Se registra solo la primera vez (ver abajo) | Únicamente **Mis tablas** (con descarga en PDF) |
| **Comprador externo** | No necesita cuenta | Página pública **`/consulta`**: escribe su cédula y ve/descarga sus tablas |

### 5.1 Dar acceso a un animador (administrador)
1. Panel → **Animadores** → botón **Editar** (lápiz) del animador.
2. Escriba su **correo institucional** y guarde. Desde ese momento puede entrar con Google.
3. Para quitarle el acceso, borre el correo y guarde.
4. **Nuevo animador** crea el animador y su cuenta de ventas a la vez.
5. **Eliminar** (papelera) borra al animador, salvo que ya tenga participantes o tablas reservadas;
   en ese caso quítele el correo.

### 5.1.1 Asignar o reasignar el curso de un animador (administrador)
**Regla:** cada curso (paralelo) tiene **un solo animador**, y cada animador **un solo curso**. El curso
se identifica por curso + especialidad + nivel + paralelo (por ejemplo, 1° F1 de Ciencias y 2° F1 de
Ciencias son cursos distintos).

1. Panel → **Animadores** → **Editar** (lápiz) → lista **Curso (paralelo)**. Cada opción dice cuántos
   alumnos tiene y si está **libre** u **ocupado por** otro animador.
2. Si elige un curso libre, se asigna al guardar.
3. Si elige un curso ocupado, el sistema pregunta si desea **reasignarlo**: al aceptar, el animador
   anterior queda **Sin curso** (no pierde su correo, sus participantes ni sus tablas).
4. **— Sin curso —** deja al animador sin paralelo.
5. Arriba se indica cuántos cursos no tienen animador, y el filtro **Sin curso** muestra los animadores
   pendientes de asignar.

### 5.1.2 Mi curso (animador)
El animador ve en **Mi curso** a los alumnos de su paralelo y puede **agregar**, **editar** (apellidos,
nombres, cédula, correo) o **eliminar** alumnos. Solo puede tocar alumnos de su propio curso y no puede
cambiarlos de curso; eso lo hace el administrador en **Estudiantes**. Si no tiene curso asignado, la
página se lo indica.

### 5.2 Reservar tablas a un animador (administrador)
Un animador solo puede vender las tablas de su rango reservado, y cada temporada las reservas
empiezan en cero.

1. Panel → **Animadores**. La columna **Tablas** muestra el rango de cada animador y cuántas usó
   (por ejemplo `CARD10951 – CARD11000 (12/50)`).
2. Si no tiene rango, pulse **Reservar** y escriba la cantidad. El sistema le asigna un bloque
   seguido de tablas libres, empezando por los seriales más altos.
3. La reserva se hace una sola vez por animador; para cambiarla hay que corregirla en la base de datos.

(El cuadro "Reservar tablas" de la página **Participantes** reserva tablas para la cuenta del
administrador, para que él mismo venda.)

### 5.3 Registro de estudiantes
1. El estudiante entra con Google con su correo estudiantil (`nombre.apellido.est@uets.edu.ec`).
2. La primera vez aparece **"Es tu primer ingreso"**: escribe **cédula, nombres y apellidos**.
3. Si coinciden con la base cargada por secretaría, su correo queda guardado y ve sus tablas.
4. Si dice "Los datos no coinciden", debe revisar cédula y nombres como constan en secretaría.
5. Si dice que la cédula ya tiene otro correo, el administrador lo corrige en **Estudiantes**
   (editar → correo).

Solo los correos estudiantiles pueden registrarse; un correo de docente sin rol recibe "sin acceso".

### 5.4 Consulta pública
`http://<dirección-del-panel>/consulta` (o `/consulta?cedula=0102030405`). No requiere cuenta.

### 5.5 Vaciar todos los participantes (administrador)
Panel → **Mantenimiento** → *Vaciar todos los participantes*. Sirve, por ejemplo, para borrar
registros de prueba antes del evento o para empezar de cero sin reiniciar toda la temporada.

1. La página muestra cuántos participantes, tablas asignadas y vendedores hay.
2. Escriba exactamente **`BORRAR PARTICIPANTES`**. El botón se activa solo entonces y pide una
   última confirmación.
3. Al confirmar:
   - se borran **todos** los participantes (alumnos, docentes y externos) de todos los animadores;
   - sus tablas quedan **libres** para volver a venderse;
   - los contadores de ventas (tablas usadas y total vendido) de cada animador vuelven a cero.
4. **No** se borran las reservas de tablas de los animadores, los estudiantes, los animadores ni el
   historial de tablas ganadoras.

Antes de borrar, el servidor guarda un respaldo en `backend\backups\participantes_<fecha>.json`, que
contiene cédulas y nombres: no lo comparta. Para restaurarlo:

```powershell
& "C:\Program Files\MongoDB\Tools\100\bin\mongoimport.exe" --db=bingo_db --collection=Participantes --file="backups\participantes_<fecha>.json"
```

Después de restaurar, las tablas siguen marcadas como libres. Si necesita el estado exacto anterior,
use el respaldo completo con `mongodump` de la sección 6.

Cada vaciado queda anotado en el registro del servidor con el correo del administrador.

### 5.6 Nuevo juego desde cero (administrador)
Panel → **Mantenimiento** → *Nuevo juego desde cero*. Deja el sistema como recién instalado para un
juego nuevo, **conservando los estudiantes y los animadores** (con sus correos y cursos).

1. La página muestra cuántas tablas, tablas asignadas, participantes y ganadoras hay ahora.
2. En **¿Cuántas tablas nuevas desea generar?** escriba la cantidad (por defecto 11000). Debajo se ve
   el rango de seriales que tendrán: `CARD00001` a `CARD<cantidad>`.
3. Escriba exactamente **`NUEVO JUEGO`**. El botón se activa solo entonces y pide una última
   confirmación con los números.
4. Al confirmar, el servidor:
   - genera las tablas nuevas y su PDF (si esto falla, **no se borra nada**);
   - guarda un respaldo en `backend\backups\nuevo_juego_<fecha>\` con las tablas, ganadoras,
     participantes y reservas que va a borrar;
   - borra **todas** las tablas, las tablas ganadoras y **todos** los participantes con sus
     asignaciones;
   - pone en cero las reservas y los contadores de ventas de los animadores;
   - guarda las tablas nuevas y deja el tablero sin cartones hasta que se vendan.
5. El **PDF de las tablas nuevas se descarga solo** para imprimirlo. Si no aparece, use **Descargar
   PDF de tablas**; el archivo también queda en el servidor, en `backend\upload\tablas_<fecha>.pdf`.

Después hay que volver a **reservar tablas** a cada animador (sección 5.2). Con 11000 tablas el
proceso tarda unos segundos. Cada reinicio queda anotado en el registro del servidor con el correo
del administrador.

> El respaldo contiene cédulas y nombres: no lo comparta. Para recuperar el estado anterior, restaure
> las colecciones de esa carpeta con `mongoimport`, o mejor use el respaldo completo con `mongodump`
> (sección 6), que conviene hacer antes de empezar un juego nuevo.

### 5.7 Reemplazar los estudiantes con el Excel de secretaría (administrador)
Panel → **Mantenimiento** → *Reemplazar estudiantes con el Excel de secretaría* (o **Estudiantes** →
**Importar Excel**).

**Plantilla:** el mismo Excel de alumnos de secretaría (p. ej. `Alumnos(2026-2027).xlsx`), en formato
`.xlsx`, primera hoja, una fila por estudiante. Se leen solo las columnas **Nombre**, **Primer
Apellido**, **Segundo Apellido**, **Curso** y **Num documento**. Los datos de padres, direcciones,
teléfonos y la columna E-mail **no** se guardan. La columna **Curso** debe venir como en la plantilla
(`EDUCACIÓN GENERAL BÁSICA Básica Media 7 A`, `BACHILLERATO Ciencias 2 BGUC F1`) y se separa en curso,
especialidad, nivel y paralelo.

1. Pulse **Elegir Excel (.xlsx)**. El servidor lo analiza **sin guardar nada** y muestra:
   - estudiantes válidos, cursos y filas con problemas (con el detalle de cada fila, que no se
     importará);
   - cuántos estudiantes siguen, cuántos son nuevos y cuántos se eliminarán;
   - cuántos correos ya registrados se conservan y cuántos se pierden (de alumnos que ya no están);
   - los animadores cuyo curso quedaría sin alumnos (revise su curso en **Animadores**).
2. Si hay **cédulas repetidas** en el Excel, no se puede importar: corríjalas y vuelva a elegirlo.
3. Escriba exactamente **`REEMPLAZAR ESTUDIANTES`** y pulse **Reemplazar**.
4. Se reemplazan **todos** los estudiantes por los del Excel. Cada estudiante que siga en el Excel
   **conserva el correo** con el que ya se registró, así que puede seguir entrando a *Mis tablas*.

No se tocan participantes, tablas ni animadores. Antes de reemplazar, el servidor guarda la lista
anterior en `backend\backups\estudiantes_<fecha>.json` (contiene cédulas y nombres: no lo comparta).
Para restaurarla:

```powershell
& "C:\Program Files\MongoDB\Tools\100\bin\mongoimport.exe" --db=bingo_db --collection=Estudiantes --drop --file="backups\estudiantes_<fecha>.json"
```

---

## 6. Inicio de temporada y respaldos

**Respaldo** (hágalo antes de cualquier cambio grande y después de cada jornada de ventas):

```powershell
& "C:\Program Files\MongoDB\Tools\100\bin\mongodump.exe" --db=bingo_db --gzip --out="backups\$(Get-Date -Format yyyy-MM-dd)"
```

**Restaurar** un respaldo (reemplaza lo actual):

```powershell
& "C:\Program Files\MongoDB\Tools\100\bin\mongorestore.exe" --gzip --drop "backups\2026-11-18_antes_temporada_2026"
```

**Nueva temporada** (borra ventas y tablas anteriores, genera tablas nuevas y carga estudiantes del Excel).
Primero simule, luego ejecute:

```powershell
env\Scripts\python scripts\nueva_temporada.py "C:\...\Alumnos(2026-2027).xlsx" --tablas 11000 --pdf "upload\tablas 2026.pdf"
env\Scripts\python scripts\nueva_temporada.py "C:\...\Alumnos(2026-2027).xlsx" --tablas 11000 --pdf "upload\tablas 2026.pdf" --ejecutar
```

Temporada 2026 actual: 11 000 tablas (`upload\tablas 2026.pdf`), 4 195 estudiantes sin correo
(se registran solos).

---

## 7. Publicar (despliegue)

### 7.1 Solo dentro del colegio (red local)
1. Encienda el servidor en la computadora servidor (sección 3).
2. **Firewall de Windows**: permita el puerto 5000 (PowerShell como administrador):
   ```powershell
   New-NetFirewallRule -DisplayName "Bingo 5000" -Direction Inbound -Protocol TCP -LocalPort 5000 -Action Allow
   ```
3. Compile el panel y sírvalo (con `API_URL` vacío en `env.js` usa la misma IP, puerto 5000):
   ```powershell
   # en bingo-system\frontend
   npm run build
   npx serve -s dist\gestor-usrs-bingo-angular\browser -l 3000
   ```
   Permita también el puerto 3000 en el firewall.
4. ⚠️ Google **no acepta IPs privadas** (`http://192.168...`) como origen de inicio de sesión. Dentro
   de la red, el login con Google solo funciona desde `http://localhost:3000` en la propia máquina.
   Para que todos entren con Google, publique con un dominio (7.2). El tablero y `/consulta` sí
   funcionan por IP.

### 7.2 Acceso desde Internet (recomendado: Cloudflare Tunnel con dominio fijo)
`cloudflared` ya está instalado en esta computadora.

- **Túnel rápido (pruebas)**:
  ```powershell
  cloudflared tunnel --url http://localhost:5000
  ```
  Da una dirección aleatoria `https://xxxx.trycloudflare.com` que **cambia cada vez**: habría que
  cambiar `env.js` del panel y volver a autorizarla en Google cada vez. Úselo solo para pruebas.
- **Túnel con nombre (evento real)**: en Cloudflare, cree un túnel con dos subdominios fijos, por
  ejemplo `api-bingo.<dominio>` → `http://localhost:5000` y `bingo.<dominio>` → `http://localhost:3000`
  (el panel servido con `npx serve`). Luego:
  1. Panel: en `dist\gestor-usrs-bingo-angular\browser\env.js` ponga
     `API_URL: 'https://api-bingo.<dominio>'` (no hace falta recompilar).
  2. Servidor `.env`: `CORS_ORIGINS=https://bingo.<dominio>` → reinicie el servidor.
  3. Google Cloud Console: agregue `https://bingo.<dominio>` en *Orígenes autorizados de JavaScript*.

  Así los estudiantes y externos usan `https://bingo.<dominio>` (login y `/consulta`).
  El **tablero** exige sesión de administrador, pero conviene usarlo dentro de la red interna.

- **Panel en HostGator (despliegue automático)**: el panel se publica en
  **<https://consultas.uets.edu.ec/>** (HostGator) en lugar de servirlo desde esta computadora. Cada cambio en `frontend/` que llega a la rama `main` de GitHub se
  compila y se sube solo por FTP. En ese caso el túnel solo necesita el subdominio del API
  (`api-bingo.<dominio>` → `http://localhost:5000`). Los pasos 2 y 3 de arriba se hacen con la
  dirección de HostGator, y el paso 1 lo hace GitHub con la variable `API_URL`. La configuración está
  en `frontend/README.md`, sección *CI/CD y despliegue en HostGator*.

### 7.3 Lista de control antes del evento
- [ ] `Get-Service MongoDB` en `Running`
- [ ] `.env` del servidor con `BINGO_SECRET_KEY` y `GOOGLE_CLIENT_ID`
- [ ] `http://localhost:5000/health` → `ok`
- [ ] Panel abre y el botón de Google funciona con `admin@uets.edu.ec`
- [ ] Animadores con correo y tablas reservadas
- [ ] Tablero: **Nuevo Juego** muestra la cantidad de tablas vendidas
- [ ] Respaldo del día hecho

---

## 8. Problemas frecuentes

| Problema | Solución |
| --- | --- |
| `ERR_ADDRESS_INVALID` al abrir `http://0.0.0.0:5000` | Use `http://localhost:5000` o la IP que muestra el servidor al arrancar. |
| Otra computadora no abre el tablero | Permita el puerto 5000 en el Firewall (7.1) y use la IP del servidor. |
| `/health` responde `503` | MongoDB está apagado: `Start-Service MongoDB`. |
| El botón de Google no aparece o da `origin_mismatch` | Falta la dirección del panel en *Orígenes autorizados de JavaScript* (2.3). |
| "El inicio de sesión con Google no está configurado" | Falta `GOOGLE_CLIENT_ID` en el `.env` del servidor. |
| "Tu cuenta no tiene acceso al sistema" | El correo no es admin, no está en **Animadores** y no es correo estudiantil. |
| "Tu sesión expiró" | Las sesiones duran 8 h (`BINGO_SESSION_HOURS`), o el servidor se reinició sin `BINGO_SECRET_KEY`. Vuelva a entrar. |
| El panel dice "Error al conectar con el servidor" | Servidor Python apagado o `API_URL` incorrecto en `env.js` del panel. |
| El tablero no muestra tablas | No hay tablas vendidas todavía, o pulse **Nuevo Juego** para cargar las ventas nuevas. |
