// Configuración del panel en tiempo de ejecución (se puede editar sin recompilar).
// Tras `npm run build` este archivo queda en dist/gestor-usrs-bingo-angular/browser/env.js.
window.__env = {
  // Dirección del servidor Python (API). Vacío = mismo equipo que abre el panel, puerto 5000.
  // Ejemplos: "http://localhost:5000", "http://192.168.200.72:5000", "https://api-bingo.midominio.com"
  API_URL: '',
  // ID de cliente OAuth de Google (no es secreto). Debe coincidir con GOOGLE_CLIENT_ID del backend.
  GOOGLE_CLIENT_ID: '579049993014-2kgtu0631odv746rvkav01ivglcgihh7.apps.googleusercontent.com',
};
