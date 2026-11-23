import { Routes } from '@angular/router';

import { guestGuard, roleGuard } from './core/guards';

const STAFF = ['admin', 'animador'] as const;
const ADMIN = ['admin'] as const;

export const routes: Routes = [
  // Login con Google
  {
    path: 'login',
    canActivate: [guestGuard],
    loadComponent: () => import('./pages/login').then((m) => m.Login),
  },
  { path: '', pathMatch: 'full', redirectTo: 'login' },

  // Páginas públicas (/buscar era la consulta anterior; conserva ?cedula=)
  { path: 'consulta', loadComponent: () => import('./pages/consulta').then((m) => m.Consulta) },
  { path: 'buscar', redirectTo: 'consulta' },

  // Estudiantes: solo sus tablas
  {
    path: 'mis-tablas',
    canActivate: [roleGuard(['estudiante'])],
    loadComponent: () => import('./pages/mis-tablas').then((m) => m.MisTablas),
  },

  // Panel (admin y animadores)
  {
    path: 'admin',
    canActivate: [roleGuard(STAFF)],
    loadComponent: () => import('./layout/admin-layout').then((m) => m.AdminLayout),
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'users' },
      { path: 'users', loadComponent: () => import('./pages/user-list').then((m) => m.UserList) },
      { path: 'add-user', loadComponent: () => import('./pages/add-user').then((m) => m.AddUser) },
      {
        path: 'user/:userId/cartones',
        loadComponent: () => import('./pages/user-cartons').then((m) => m.UserCartons),
      },
      {
        path: 'user/:userId/add-carton',
        loadComponent: () => import('./pages/add-carton').then((m) => m.AddCarton),
      },
      {
        path: 'cartones',
        loadComponent: () => import('./pages/carton-search').then((m) => m.CartonSearch),
      },
      {
        path: 'cartones/:cartonId',
        loadComponent: () => import('./pages/carton-view').then((m) => m.CartonView),
      },
      {
        path: 'buscar-participante',
        loadComponent: () =>
          import('./pages/buscar-participante').then((m) => m.BuscarParticipante),
      },
      // Alumnos del curso asignado al animador
      { path: 'mi-curso', loadComponent: () => import('./pages/mi-curso').then((m) => m.MiCurso) },
      // Solo administrador
      {
        path: 'reportes',
        canActivate: [roleGuard(ADMIN)],
        loadComponent: () => import('./pages/reports').then((m) => m.Reports),
      },
      {
        path: 'animadores',
        canActivate: [roleGuard(ADMIN)],
        loadComponent: () => import('./pages/animadores-admin').then((m) => m.AnimadoresAdmin),
      },
      {
        path: 'estudiantes',
        canActivate: [roleGuard(ADMIN)],
        loadComponent: () => import('./pages/estudiantes-admin').then((m) => m.EstudiantesAdmin),
      },
      {
        path: 'mantenimiento',
        canActivate: [roleGuard(ADMIN)],
        loadComponent: () => import('./pages/mantenimiento').then((m) => m.Mantenimiento),
      },
    ],
  },

  // Cualquier otra ruta → login
  { path: '**', redirectTo: 'login' },
];
