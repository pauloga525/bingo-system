# Bingo UETS

Sistema de bingo de la UETS: tablero del juego, venta y asignación de tablas, login con Google
(admin, animador y estudiante) y consulta pública de tablas por cédula.

| Carpeta | Qué es | Tecnología | Dirección local |
| --- | --- | --- | --- |
| [`backend/`](backend/) | Servidor del juego y API | Python (Flask) + MongoDB | `http://localhost:5000` |
| [`frontend/`](frontend/) | Panel web | Angular 21 | `http://localhost:3000` |

📘 **Manual de uso** (encender, jugar, ingresar y publicar): [backend/docs/MANUAL.md](backend/docs/MANUAL.md)

## Inicio rápido

```powershell
# Servidor (requiere Python 3.11+ y MongoDB). Copie .env.example a .env y complete los valores.
cd backend
python -m venv env
env\Scripts\pip install -r requirements.txt
.\iniciar_servidor.ps1
```

```powershell
# Panel (requiere Node.js 20.19+). La dirección del API se configura en public/env.js.
cd frontend
npm install
npm start
```

> Los archivos `.env`, los respaldos de la base de datos, los Excel de secretaría y los PDF de
> tablas contienen credenciales o datos personales y **nunca** se suben al repositorio.
