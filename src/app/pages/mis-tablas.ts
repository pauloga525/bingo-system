// Vista del estudiante: sus tablas, enlazadas por su cédula.
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { LogOut, LucideAngularModule } from 'lucide-angular';
import { firstValueFrom } from 'rxjs';

import { errorMessage } from '../core/http';
import { SessionService } from '../core/session';
import { Tabla } from '../core/tablas';
import { TablasGrid } from '../shared/tablas-grid';

interface MisTablasResponse {
  estudiante?: { nombre?: string; cedula?: string };
  tablas: Tabla[];
}

@Component({
  selector: 'app-mis-tablas',
  imports: [LucideAngularModule, TablasGrid],
  template: `
    <div class="min-h-screen bg-gray-50 dark:bg-gray-900">
      <header
        class="flex items-center justify-between border-b border-gray-200 dark:border-gray-700 px-6 py-3 bg-white dark:bg-gray-900"
      >
        <h2 class="text-lg font-bold text-gray-900 dark:text-white">Mis tablas de Bingo</h2>
        <div class="flex items-center gap-3">
          <span class="text-sm text-gray-600 dark:text-gray-300">{{
            usuario()?.nombres || usuario()?.correo
          }}</span>
          <button
            type="button"
            (click)="logout()"
            title="Cerrar sesión"
            class="flex w-10 h-10 items-center justify-center rounded-full bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300"
          >
            <lucide-icon [img]="LogOutIcon" [size]="20" />
          </button>
        </div>
      </header>

      <main class="max-w-5xl mx-auto p-6">
        @if (error()) {
          <p class="text-red-600">{{ error() }}</p>
        } @else if (!data()) {
          <p class="text-gray-600">Cargando...</p>
        }
        @if (data(); as d) {
          <div class="bg-white dark:bg-gray-800 rounded-2xl shadow p-6">
            <p class="text-gray-700 dark:text-gray-200 mb-4">
              {{ d.estudiante?.nombre }} · Cédula {{ d.estudiante?.cedula }}
            </p>
            <app-tablas-grid
              [tablas]="d.tablas"
              [titulo]="'Bingo UETS - ' + (d.estudiante?.nombre || '')"
              [archivo]="'tablas_' + (d.estudiante?.cedula || 'estudiante') + '.pdf'"
            />
          </div>
        }
      </main>
    </div>
  `,
})
export class MisTablas implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private readonly session = inject(SessionService);
  protected readonly LogOutIcon = LogOut;

  protected readonly usuario = this.session.user;
  protected readonly data = signal<MisTablasResponse | null>(null);
  protected readonly error = signal('');

  async ngOnInit(): Promise<void> {
    try {
      this.data.set(await firstValueFrom(this.http.get<MisTablasResponse>('/api/mis-tablas')));
    } catch (err) {
      this.error.set(errorMessage(err, 'No se pudieron cargar tus tablas.'));
    }
  }

  protected logout(): void {
    this.session.clear();
    void this.router.navigateByUrl('/login');
  }
}
