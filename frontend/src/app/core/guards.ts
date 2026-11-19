// Protección de rutas por rol.
import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { ROLES, Rol, SessionService, homeFor } from './session';

/** Permite la ruta solo a los ``roles`` indicados; si no, envía al login o a su inicio. */
export const roleGuard =
  (roles: readonly Rol[]): CanActivateFn =>
  () => {
    const session = inject(SessionService);
    const router = inject(Router);
    if (!session.isLoggedIn()) return router.parseUrl('/login');
    const role = session.role();
    if (!role || !ROLES.includes(role)) {
      // Sesión antigua (login con contraseña) o dañada: pedir login de nuevo.
      session.clear();
      return router.parseUrl('/login');
    }
    return roles.includes(role) ? true : router.parseUrl(homeFor(session.user()));
  };

/** En /login: si ya hay sesión, ir directo al inicio del rol. */
export const guestGuard: CanActivateFn = () => {
  const session = inject(SessionService);
  return session.isLoggedIn() ? inject(Router).parseUrl(homeFor(session.user())) : true;
};
