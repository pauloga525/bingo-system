// Interceptor HTTP: URL base del API, token de sesión y cierre de sesión ante 401.
import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';

import { API_BASE_URL } from './config';
import { SessionService } from './session';

export const apiInterceptor: HttpInterceptorFn = (req, next) => {
  const session = inject(SessionService);
  const token = session.token();
  const isApi = req.url.startsWith('/');
  let request = isApi ? req.clone({ url: API_BASE_URL + req.url }) : req;
  if (isApi && token) {
    request = request.clone({ setHeaders: { Authorization: `Bearer ${token}` } });
  }
  return next(request).pipe(
    catchError((err: unknown) => {
      // Sesión expirada o revocada: volver al login.
      if (err instanceof HttpErrorResponse && err.status === 401 && token) {
        session.clear();
        if (location.pathname !== '/login') location.assign('/login?expirada=1');
      }
      return throwError(() => err);
    }),
  );
};

/** Mensaje de error del backend (``{message}``) o el texto por defecto. */
export const errorMessage = (err: unknown, fallback: string): string => {
  if (err instanceof HttpErrorResponse) {
    const msg = (err.error as { message?: unknown } | null)?.message;
    if (typeof msg === 'string' && msg) return msg;
  }
  return fallback;
};

/** Cuerpo JSON del error HTTP (o null). */
export const errorBody = <T = Record<string, unknown>>(err: unknown): T | null =>
  err instanceof HttpErrorResponse && err.error && typeof err.error === 'object'
    ? (err.error as T)
    : null;

/** Respuesta 409 del servidor (otra venta se llevó las tablas, cédula ya registrada, ...). */
export const isConflict = (err: unknown): boolean =>
  err instanceof HttpErrorResponse && err.status === 409;

/** Deja solo los dígitos de un texto. */
export const onlyDigits = (value: unknown): string => String(value ?? '').replace(/\D/g, '');
