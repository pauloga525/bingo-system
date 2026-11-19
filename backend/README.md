# 🎱 SISTEMA PARA BINGO

Sistema web para la gestión y administración de juegos de bingo, pensado para facilitar la generación, control y seguimiento de cartones, ganadores y partidas. Ideal para eventos, rifas, asociaciones y actividades recreativas.

---

> 📘 **Manual de uso (encender, jugar, ingresar y publicar): [docs/MANUAL.md](docs/MANUAL.md)**

## 📑 Tabla de Contenido

- [Características principales](#características-principales)
- [Instalación](#instalación)
- [Uso](#uso)
- [Configuración adicional](#configuración-adicional)
- [Notas importantes](#notas-importantes)
- [Créditos](#créditos)
- [Licencia](#licencia)

---

## 🚀 Características principales

- Generación masiva de cartones de bingo en formato JSON.
- Registro y control de ganadores.
- Interfaz web intuitiva para visualizar y administrar partidas.
- Carga y gestión de archivos de cartones.
- Exportación de resultados y reportes.
- Soporte para múltiples partidas y eventos.
- Sistema de archivos organizado para cartones, ganadores y archivos subidos.

---

## 🛠️ Instalación

> Requiere Python 3.11+ y MongoDB.

```bash
git clone https://github.com/pauloga525/bingo-system.git
cd bingo-system/backend
python -m venv env
env\Scripts\activate            # Windows  (Linux/macOS: source env/bin/activate)
pip install -r requirements.txt  # producción
pip install -r requirements-dev.txt  # desarrollo (tests, ruff, mypy)
```

La configuración se lee de variables de entorno; los valores por defecto están en `.env.example`
(MongoDB local, puerto 5000, **debug desactivado**).

---

## 🏗️ Arquitectura

```
app.py                  Punto de entrada (servidor + CLI). Expone `app` para WSGI.
bingo/
  __init__.py           create_app(): fábrica de Flask, CORS, blueprints, errores
  config.py             Settings (variables de entorno)
  auth.py               Login con Google, token de sesión, roles y control de acceso de /api
  db.py                 Colecciones de MongoDB e índices
  errors.py             ApiError y manejadores JSON centralizados
  utils.py              Conversión de ids, serialización de documentos
  domain/               Reglas puras, sin I/O (fáciles de testear)
    cards.py            Generación de cartones, aciertos, regla de victoria
    pricing.py          calcular_total(): ÚNICA regla de cobro
    serials.py          Seriales CARDNNNNN y rangos por usuario
  services/             Casos de uso (lógica de negocio + MongoDB)
    participants.py     Registro, agregar/quitar tablas, eliminar (con contadores)
    users.py            Reservas de tablas y auditoría de contadores
    animators.py        CRUD de Animadores (enlazado a su cuenta de Users)
    students.py         CRUD de Estudiantes y tablas de un estudiante
    tables.py           Consultas de tablas y búsqueda de estudiantes/docentes
    reports.py          Reporte general
    game.py             Partida en curso (snapshot JSON), generación e importación
    pdf_render.py       PDFs de cartones y de ganador (layout compartido)
    pdf_extract.py      Lectura de cartones desde PDF
  routes/               Blueprints HTTP delgados (solo traducen request/response)
tests/                  pytest + mongomock
scripts/                Scripts de mantenimiento (ver abajo)
docs/                   Notas históricas de cambios
```

## 🔐 Inicio de sesión con Google

El login con usuario y contraseña se reemplazó por **Google (OAuth 2.0 / OpenID Connect)**.
El frontend (Angular, carpeta `frontend/` de este repo) obtiene un *ID token* de Google y lo envía a `POST /api/auth/google`;
el backend lo verifica (firma, `GOOGLE_CLIENT_ID`, cuenta de Google Workspace) y devuelve un token de
sesión firmado (`BINGO_SECRET_KEY`, `BINGO_SESSION_HOURS` horas) que se envía en
`Authorization: Bearer <token>` en cada llamada a `/api`.

| Rol | Quién | Cómo se autoriza |
| --- | --- | --- |
| admin | `BINGO_ADMIN_EMAILS` (por defecto `admin@uets.edu.ec`) | Usa la cuenta `BINGO_ADMIN_USUARIO` de `Users` |
| animador | correo `@uets.edu.ec` guardado en el campo `correo` de `Animadores` | Se enlaza a su cuenta de `Users` (`usuario_id`) |
| estudiante | correo `nombre.apellido.est@uets.edu.ec` guardado en el campo `correo` de `Estudiantes` | Solo ve sus tablas (`GET /api/mis-tablas`) |

**Registro de estudiantes.** Los estudiantes se cargan sin correo. La primera vez que un estudiante entra con
Google y su correo es estudiantil (`...est@uets.edu.ec`, `..._estudiante@uets.edu.ec` o `@est.uets.edu.ec`), el
backend responde `403` con `registro_requerido` y un token de 30 minutos ligado a ese correo verificado. El
estudiante escribe su cédula, nombres y apellidos (`POST /api/auth/registro`); si la cédula existe, el primer
nombre y el primer apellido coinciden (sin importar tildes ni mayúsculas) y la cédula no tiene otro correo, se
guarda el correo y queda con sesión iniciada. Otros correos `@uets.edu.ec` sin rol no pueden registrarse.

Cualquier otro correo recibe 403. Si se quita el correo de un animador pierde el acceso en su próxima petición.
Los animadores solo pueden operar en su propio nombre (`usuario_id`, `registrado_por`, `requesting_user_id`).

Endpoints nuevos:
- `GET /api/auth/config` (público), `POST /api/auth/google`, `GET /api/auth/me`
- `GET|POST /api/animadores`, `GET|PUT|DELETE /api/animadores/<id>` (admin)
- `GET|POST /api/estudiantes?search=&page=&per_page=`, `GET|PUT|DELETE /api/estudiantes/<id>` (admin)
- `GET /api/mis-tablas` (estudiante)
- `GET /api/consulta/<cedula>` (**público**: solo nombre y tablas del comprador)

Se eliminaron `POST /api/login` y `POST /api/users/announcer` (reemplazado por el CRUD de animadores).
`/api/reportes`, `/api/validar-tablas/*` y `/api/users/*/assign_tables` ahora son solo para el admin.

**Configuración en Google Cloud Console** (credencial OAuth "Aplicación web"): agrega en
*Orígenes autorizados de JavaScript* cada URL desde la que se abre el frontend
(p. ej. `http://localhost:3000` y el dominio público).

---

## 💻 Uso

```bash
python app.py                # reconstruye la partida desde MongoDB e inicia el servidor
python app.py 100            # genera 100 cartones en bingo_cards.json (no toca la BD)
python app.py cartones.pdf   # extrae los cartones de un PDF a bingo_cards.json
```

Sin `FLASK_DEBUG=true`, `python app.py` sirve con **waitress** (servidor de producción, `BINGO_THREADS` hilos).
`GET /health` responde `200` si MongoDB está disponible y `503` si no (útil para monitoreo).

### Flujo de la partida
1. `POST /reset` crea `jsons/bingo_cards_active_<ts>.json` con las tablas **asignadas y no ganadoras**.
2. `/mark` y `/progress` trabajan siempre sobre ese snapshot (el más reciente `bingo_cards_active_*`).
3. Gana la **tabla llena** (25 aciertos). El ganador se guarda en `tablas_ganadoras` y la tabla queda `won: true`.

### Seguridad de datos
- `/generate` se niega (409) a regenerar seriales que ya existen, porque cambiaría cartones impresos.
  Con `"force": true` lo permite solo si ninguna de esas tablas está asignada.
- `/upload` nunca reinicia `won`/`stateAsigned`; si una tabla asignada viene con otra matriz, no se modifica
  y se reporta en `conflictos_asignadas`.
- Los permisos (admin / dueño del participante) se validan con el usuario guardado en la BD,
  no con el `tipo_usuario` que llega en la URL.
- `/upload` solo acepta PDF (cabecera `%PDF-`) de hasta `BINGO_MAX_UPLOAD_MB` MB (50 por defecto) y no
  expone detalles internos si falla; `/generate` acepta entre 1 y 99 999 cartones.
- Todas las respuestas llevan `X-Content-Type-Options`, `X-Frame-Options` y `Referrer-Policy`.

> ⚠️ **Pendiente:** las rutas de la mesa de juego (`/reset`, `/generate`, `/upload`, `/mark`, ...) siguen
> sin autenticación porque las usa la pantalla del juego (`templates/index.html`). Expón el servidor solo
> en una red de confianza y restringe `CORS_ORIGINS`.

### Mantenimiento
```bash
python scripts/nueva_temporada.py "Alumnos(2026-2027).xlsx" --tablas 11000 --pdf "upload/tablas 2026.pdf"  # simula; --ejecutar aplica
python scripts/diagnostico_consistencia.py   # SOLO LECTURA: tablas duplicadas, contadores desfasados, etc.
python scripts/check_db_connection.py        # prueba la conexión con MONGO_URI / MONGO_DB
```
Todos los scripts usan la misma configuración que la app (`MONGO_URI`, `MONGO_DB`) mediante `scripts/_common.py`.
`GET /api/validar-tablas/<usuario_id>` muestra el diagnóstico de un usuario; `POST` corrige
`usedTables`, `total_vendido` y el `total_pagar` de sus participantes.

### Calidad
```bash
pytest --cov                          # falla si la cobertura baja de 90 %
ruff check . && ruff format --check . # estilo, complejidad (máx. 8) y reglas de seguridad (bandit)
mypy                                  # tipado estricto
pip-audit -r requirements.txt         # vulnerabilidades conocidas en dependencias
pre-commit install                    # ejecuta ruff y mypy antes de cada commit
```
GitHub Actions (`.github/workflows/ci.yml`) corre todo lo anterior en cada push a `main` y en cada PR.
Las dependencias de `requirements.txt` están fijadas a versiones auditadas.

---

## ❗ Notas importantes

- No subas archivos con credenciales o datos personales (`users-passwords.json`, `animadores.json`, reportes).
- `jsons/`, `upload/` y `winners/` se ignoran en Git.
- Solo un admin (tipo_usuario = 0) puede reservar tablas; se toman desde el último código hacia atrás
  (ej. CARD11000, CARD10999, ...), por eso `fromSerial` puede ser mayor que `toSerial`.

---

## 👥 Créditos

Desarrollado por [Paulo Gonzalez](https://github.com/paulogonzalez5679).


---

## 📄 Licencia

Este proyecto está bajo la licencia BSD-3. Consulta el archivo `LICENSE` para más detalles.

---

¡Gracias por usar SISTEMA PARA BINGO! 🎉
