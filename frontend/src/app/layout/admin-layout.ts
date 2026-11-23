// Marco del panel (admin y animadores): encabezado con menú + contenido de la ruta.
import { Component, computed, inject } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { LogOut, LucideAngularModule, Monitor, User } from 'lucide-angular';

import { API_BASE_URL } from '../core/config';
import { SessionService } from '../core/session';

@Component({
  selector: 'app-admin-layout',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, LucideAngularModule],
  template: `
    <div class="min-h-screen bg-gray-50 dark:bg-gray-900 flex flex-col">
      <header
        class="flex flex-wrap items-center justify-between gap-3 border-b border-gray-200 dark:border-gray-700 px-6 lg:px-10 py-3 bg-white dark:bg-gray-900"
      >
        <a routerLink="/admin/users" class="flex items-center gap-3">
          <span class="text-blue-600 w-7 h-7 flex items-center justify-center">
            <svg fill="none" viewBox="0 0 48 48">
              <path
                d="M24 4C25.7818 14.2173 33.7827 22.2182 44 24C33.7827 25.7818 25.7818 33.7827 24 44C22.2182 33.7827 14.2173 25.7818 4 24C14.2173 22.2182 22.2182 14.2173 24 4Z"
                fill="currentColor"
              />
            </svg>
          </span>
          <span class="text-lg font-bold text-gray-900 dark:text-white">Bingo UETS</span>
        </a>

        <nav class="flex flex-wrap items-center gap-x-6 gap-y-1">
          @for (link of links(); track link.path) {
            <a
              [routerLink]="link.path"
              routerLinkActive="!text-blue-600"
              class="text-sm font-medium text-gray-600 hover:text-blue-600 dark:text-gray-300"
              >{{ link.label }}</a
            >
          }
        </nav>

        <div class="flex items-center gap-4">
          @if (isAdmin()) {
            <button
              type="button"
              (click)="abrirTablero()"
              title="Abrir el tablero del juego en otra pestaña"
              class="flex items-center gap-2 px-3 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-medium"
            >
              <lucide-icon [img]="MonitorIcon" [size]="16" /> Tablero
            </button>
          }
          @if (userName()) {
            <div class="flex items-center gap-2 px-3 py-2 bg-gray-100 dark:bg-gray-800 rounded-lg">
              <lucide-icon [img]="UserIcon" [size]="16" class="text-gray-600 dark:text-gray-400" />
              <span class="text-sm font-medium text-gray-700 dark:text-gray-300">{{
                userName()
              }}</span>
            </div>
          }
          <button
            type="button"
            (click)="logout()"
            title="Cerrar sesión"
            class="flex w-10 h-10 items-center justify-center rounded-full bg-gray-100 text-gray-600 hover:scale-105 transition dark:bg-gray-800 dark:text-gray-300"
          >
            <lucide-icon [img]="LogOutIcon" [size]="20" />
          </button>
        </div>
      </header>
      <main class="flex-1">
        <router-outlet />
      </main>
    </div>
  `,
})
export class AdminLayout {
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);
  protected readonly UserIcon = User;
  protected readonly LogOutIcon = LogOut;
  protected readonly MonitorIcon = Monitor;
  protected readonly isAdmin = this.session.isAdmin;

  protected readonly userName = computed(() => {
    const u = this.session.user();
    return u ? u.nombres || u.usuario || u.correo || 'Usuario' : '';
  });

  protected readonly links = computed(() => [
    { path: '/admin/users', label: 'Participantes' },
    { path: '/admin/buscar-participante', label: 'Buscar' },
    { path: '/admin/cartones', label: 'Cartones' },
    ...(this.session.isAdmin() ? [] : [{ path: '/admin/mi-curso', label: 'Mi curso' }]),
    ...(this.session.isAdmin()
      ? [
          { path: '/admin/reportes', label: 'Reportes' },
          { path: '/admin/animadores', label: 'Animadores' },
          { path: '/admin/estudiantes', label: 'Estudiantes' },
          { path: '/admin/mantenimiento', label: 'Mantenimiento' },
        ]
      : []),
  ]);

  /**
   * Abre el tablero del juego (servidor Python) en otra pestaña con la sesión del admin.
   * El token va en un formulario POST, nunca en la URL.
   */
  protected abrirTablero(): void {
    const form = document.createElement('form');
    form.method = 'POST';
    form.action = `${API_BASE_URL}/tablero/sesion`;
    form.target = '_blank';
    const token = document.createElement('input');
    token.type = 'hidden';
    token.name = 'token';
    token.value = this.session.token() || '';
    form.appendChild(token);
    document.body.appendChild(form);
    form.submit();
    form.remove();
  }

  protected logout(): void {
    this.session.clear();
    void this.router.navigateByUrl('/login');
  }
}
