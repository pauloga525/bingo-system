// Participantes registrados por el usuario conectado. Las tablas se venden en cola (sin reservas).
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { Edit, Loader, LucideAngularModule, Plus, Search, Trash2 } from 'lucide-angular';
import { firstValueFrom } from 'rxjs';

import { errorMessage } from '../core/http';
import { SessionService } from '../core/session';

export interface Participante {
  _id: string;
  nombre?: string;
  apellido?: string;
  cedula?: string;
  nivelCurso?: string;
  paralelo?: string;
  tablas?: unknown[];
}

interface UsuarioDoc {
  usedTables?: number;
  total_vendido?: number;
}

/** Estado de la cola única de tablas. */
interface Cola {
  total: number;
  vendidas: number;
  disponibles: number;
  siguiente: string | null;
}

interface PorUsuarioResponse {
  success: boolean;
  message?: string;
  participantes?: Participante[];
  usuario?: UsuarioDoc;
}

const TH = 'px-6 py-3 text-left text-xs font-semibold uppercase text-gray-500 dark:text-gray-400';

@Component({
  selector: 'app-user-list',
  imports: [RouterLink, LucideAngularModule],
  template: `
    @if (loading()) {
      <div class="p-6 lg:p-10 flex items-center justify-center min-h-[60vh]">
        <lucide-icon [img]="LoaderIcon" [size]="32" class="animate-spin text-blue-500" />
      </div>
    } @else if (error()) {
      <div class="p-6 lg:p-10">
        <div class="bg-red-100 border border-red-400 text-red-700 px-4 py-3 rounded">
          {{ error() }}
        </div>
      </div>
    } @else {
      <div class="p-6 lg:p-10">
        <div class="mb-6 flex flex-wrap items-center justify-between gap-4">
          <h1 class="text-3xl font-bold text-gray-900 dark:text-white">Gestionar Participantes</h1>

          <div class="flex flex-wrap items-center gap-4">
            <div class="text-sm text-gray-700 dark:text-gray-300">
              Tus ventas: <strong>{{ usuarioDoc()?.usedTables || 0 }}</strong> tablas
              @if (cola(); as c) {
                <span>
                  | Cola: <strong>{{ c.disponibles }}</strong> de {{ c.total }} disponibles
                  @if (c.siguiente) {
                    · próxima <strong>{{ c.siguiente }}</strong>
                  }
                </span>
              }
            </div>

            <button
              type="button"
              (click)="anadir()"
              [disabled]="!cola()?.disponibles"
              class="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg font-bold hover:bg-blue-700 disabled:opacity-60"
            >
              <lucide-icon [img]="PlusIcon" [size]="16" /> Añadir Participante
            </button>
          </div>
        </div>

        <div class="mb-6 relative">
          <lucide-icon
            [img]="SearchIcon"
            [size]="16"
            class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
          />
          <input
            type="text"
            [value]="search()"
            (input)="search.set($any($event.target).value)"
            placeholder="Buscar participantes por nombre, apellido o cédula"
            class="w-full pl-10 pr-4 py-2.5 border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-800 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
        </div>

        <div
          class="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900"
        >
          <table class="w-full">
            <thead class="bg-gray-50 dark:bg-gray-800">
              <tr>
                <th [class]="th">Nivel</th>
                <th [class]="th">Paralelo</th>
                <th [class]="th">Nombre</th>
                <th [class]="th">Apellido</th>
                <th [class]="th">Cédula</th>
                <th [class]="th">Cartones Registrados</th>
                <th [class]="th">Acciones</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-gray-200 dark:divide-gray-700">
              @for (p of filtrados(); track p._id) {
                <tr>
                  <td class="px-6 py-4 text-sm font-medium text-gray-900 dark:text-white">
                    {{ p.nivelCurso || '-' }}
                  </td>
                  <td class="px-6 py-4 text-sm font-medium text-gray-900 dark:text-white">
                    {{ p.paralelo || '-' }}
                  </td>
                  <td class="px-6 py-4 text-sm font-medium text-gray-900 dark:text-white">
                    {{ p.nombre || '-' }}
                  </td>
                  <td class="px-6 py-4 text-sm text-gray-600 dark:text-gray-300">
                    {{ p.apellido || '-' }}
                  </td>
                  <td class="px-6 py-4 text-sm text-gray-600 dark:text-gray-300">
                    {{ p.cedula || '-' }}
                  </td>
                  <td class="px-6 py-4 text-sm text-gray-600 dark:text-gray-300">
                    {{ (p.tablas || []).length }}
                  </td>
                  <td class="px-6 py-4 text-sm">
                    <div class="flex gap-4">
                      <a
                        [routerLink]="['/admin/user', p._id, 'cartones']"
                        class="flex items-center gap-1 text-blue-600 hover:underline"
                      >
                        <lucide-icon [img]="EditIcon" [size]="16" /> Ver Cartones
                      </a>
                      <button
                        type="button"
                        (click)="eliminar(p)"
                        class="flex items-center gap-1 text-red-600 hover:underline"
                      >
                        <lucide-icon [img]="TrashIcon" [size]="16" /> Borrar
                      </button>
                    </div>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="7" class="px-6 py-4 text-center text-gray-500">
                    No hay participantes registrados
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      </div>
    }
  `,
})
export class UserList implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private readonly session = inject(SessionService);
  protected readonly LoaderIcon = Loader;
  protected readonly PlusIcon = Plus;
  protected readonly SearchIcon = Search;
  protected readonly EditIcon = Edit;
  protected readonly TrashIcon = Trash2;
  protected readonly th = TH;

  protected readonly isAdmin = this.session.isAdmin;
  protected readonly participantes = signal<Participante[]>([]);
  protected readonly usuarioDoc = signal<UsuarioDoc | null>(null);
  protected readonly search = signal('');
  protected readonly cola = signal<Cola | null>(null);
  protected readonly loading = signal(true);
  protected readonly error = signal('');

  protected readonly filtrados = computed(() => {
    const q = this.search().toLowerCase();
    return this.participantes().filter(
      (p) =>
        (p.nombre || '').toLowerCase().includes(q) ||
        (p.apellido || '').toLowerCase().includes(q) ||
        (p.cedula || '').includes(q),
    );
  });

  ngOnInit(): void {
    void this.cargar(true);
  }

  private get userId(): string {
    return this.session.user()?.id || '';
  }

  /** Recarga participantes, ventas del usuario y el estado de la cola. */
  private async cargar(showSpinner = false): Promise<UsuarioDoc | null> {
    if (showSpinner) this.loading.set(true);
    try {
      const resp = await firstValueFrom(
        this.http.get<PorUsuarioResponse>(`/api/participantes/por-usuario/${this.userId}`),
      );
      if (!resp.success) {
        this.error.set(resp.message || 'Error al cargar participantes');
        return null;
      }
      this.participantes.set(resp.participantes || []);
      this.usuarioDoc.set(resp.usuario || {});
      this.cola.set(await firstValueFrom(this.http.get<Cola>('/api/cola-tablas')));
      return resp.usuario || {};
    } catch (err) {
      this.error.set(errorMessage(err, 'Error al conectar con el servidor'));
      return null;
    } finally {
      this.loading.set(false);
    }
  }

  protected async anadir(): Promise<void> {
    await this.cargar();
    if (!this.cola()?.disponibles) {
      alert('Ya no quedan tablas disponibles para vender.');
      return;
    }
    void this.router.navigate(['/admin/add-user']);
  }

  protected async eliminar(p: Participante): Promise<void> {
    if (!confirm('¿Está seguro de eliminar este participante?')) return;
    const user = this.session.user();
    try {
      const resp = await firstValueFrom(
        this.http.delete<{ success: boolean; message?: string }>(
          `/api/participante/${p._id}/${user?.tipo_usuario}`,
          { body: { usuario_id: user?.id } },
        ),
      );
      if (resp.success) {
        alert('Participante eliminado correctamente');
        await this.cargar();
      } else {
        alert(resp.message || 'Error al eliminar participante');
      }
    } catch (err) {
      alert(errorMessage(err, 'Error al eliminar participante'));
    }
  }
}
