// Cartones (tablas) de un participante.
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import {
  ArrowLeft,
  Award,
  Eye,
  Loader,
  LucideAngularModule,
  Plus,
  Search,
  Trash2,
  X,
} from 'lucide-angular';
import { firstValueFrom } from 'rxjs';

import { errorMessage } from '../core/http';
import { SessionService } from '../core/session';
import { Tabla } from '../core/tablas';
import { Participante } from './user-list';

@Component({
  selector: 'app-user-cartons',
  imports: [RouterLink, LucideAngularModule],
  template: `
    @if (loading()) {
      <div class="p-6 lg:p-10 flex items-center justify-center min-h-[60vh]">
        <lucide-icon [img]="LoaderIcon" [size]="32" class="animate-spin text-blue-500" />
      </div>
    } @else if (!participante()) {
      <div class="p-6 lg:p-10 text-gray-700 dark:text-gray-200">Participante no encontrado</div>
    } @else {
      <div class="p-6 lg:p-10">
        <div class="mb-8">
          <a
            routerLink="/admin/users"
            class="flex items-center gap-2 text-sm text-gray-600 hover:text-yellow-500 mb-4"
          >
            <lucide-icon [img]="ArrowLeftIcon" [size]="16" /> Volver a Participantes
          </a>
          <div class="flex flex-wrap items-center justify-between gap-4">
            <div>
              <h1 class="text-3xl font-bold text-gray-900 dark:text-white">
                Cartones de {{ participante()?.nombre || '' }} {{ participante()?.apellido || '' }}
              </h1>
              <p class="text-gray-600 dark:text-gray-300">
                Cédula: {{ participante()?.cedula || '-' }}
              </p>
            </div>
            <a
              [routerLink]="['/admin/user', userId(), 'add-carton']"
              class="flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg font-bold"
            >
              <lucide-icon [img]="PlusIcon" [size]="16" /> Añadir Cartón
            </a>
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
            placeholder="Buscar por código de cartón"
            class="w-full pl-10 pr-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
          />
        </div>

        <div class="overflow-x-auto rounded-lg border bg-white dark:bg-gray-900">
          <table class="w-full">
            <thead class="bg-gray-50 dark:bg-gray-800">
              <tr>
                <th class="px-6 py-3 text-left text-xs font-semibold text-yellow-500">
                  Código del Cartón
                </th>
                <th class="px-6 py-3 text-left text-xs font-semibold text-yellow-500">Estado</th>
                <th class="px-6 py-3 text-left text-xs font-semibold text-yellow-500">Acciones</th>
              </tr>
            </thead>
            <tbody>
              @for (carton of filtrados(); track carton._id) {
                <tr>
                  <td class="px-6 py-4 text-sm font-medium text-gray-900 dark:text-white">
                    {{ carton.serial || '-' }}
                  </td>
                  <td class="px-6 py-4 text-sm">
                    <span
                      class="inline-flex items-center gap-1 px-2 py-1 rounded-full font-medium"
                      [class]="
                        carton.won
                          ? 'bg-green-100 text-green-500 dark:bg-green-800'
                          : 'bg-red-100 text-red-500 dark:bg-red-800'
                      "
                    >
                      <lucide-icon [img]="carton.won ? AwardIcon : XIcon" [size]="18" />
                      {{ carton.won ? 'Ganadora' : 'Sin Premio' }}
                    </span>
                  </td>
                  <td class="px-6 py-4">
                    <div class="flex gap-4">
                      <a
                        [routerLink]="['/admin/cartones', carton._id]"
                        class="flex items-center gap-1 text-blue-600 hover:underline"
                      >
                        <lucide-icon [img]="EyeIcon" [size]="16" /> Ver
                      </a>
                      <button
                        type="button"
                        (click)="eliminar(carton)"
                        class="flex items-center gap-1 text-red-600 hover:underline"
                      >
                        <lucide-icon [img]="TrashIcon" [size]="16" /> Borrar
                      </button>
                    </div>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="3" class="px-6 py-4 text-center text-gray-500">
                    No hay cartones asignados a este participante
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
export class UserCartons implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);
  protected readonly ArrowLeftIcon = ArrowLeft;
  protected readonly AwardIcon = Award;
  protected readonly EyeIcon = Eye;
  protected readonly LoaderIcon = Loader;
  protected readonly PlusIcon = Plus;
  protected readonly SearchIcon = Search;
  protected readonly TrashIcon = Trash2;
  protected readonly XIcon = X;

  /** Parámetro de ruta :userId (id del participante). */
  readonly userId = input.required<string>();

  protected readonly participante = signal<Participante | null>(null);
  protected readonly cartones = signal<Tabla[]>([]);
  protected readonly loading = signal(true);
  protected readonly search = signal('');
  protected readonly filtrados = computed(() => {
    const q = this.search().toLowerCase();
    return this.cartones().filter((c) => (c.serial || '').toLowerCase().includes(q));
  });

  ngOnInit(): void {
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    const user = this.session.user();
    try {
      const resp = await firstValueFrom(
        this.http.get<{ success: boolean; tablas?: Tabla[] }>(
          `/api/obtenerTablasParticipante/${this.userId()}`,
        ),
      );
      if (!resp.success) return;
      this.cartones.set(resp.tablas || []);
      const lista = await firstValueFrom(
        this.http.get<{ success: boolean; participantes?: Participante[] }>('/api/participantes', {
          params: { usuario_id: user?.id || '', tipo_usuario: String(user?.tipo_usuario ?? '') },
        }),
      );
      if (lista.success) {
        this.participante.set(
          (lista.participantes || []).find((p) => p._id === this.userId()) || null,
        );
      }
    } catch (err) {
      alert(errorMessage(err, 'Error al cargar los cartones del participante'));
    } finally {
      this.loading.set(false);
    }
  }

  protected async eliminar(carton: Tabla): Promise<void> {
    if (!confirm('¿Está seguro de eliminar esta tabla del participante?')) return;
    const user = this.session.user();
    try {
      const resp = await firstValueFrom(
        this.http.delete<{ success: boolean; message?: string }>(
          `/api/participante/${this.userId()}/tabla/${carton._id}/${user?.tipo_usuario}`,
          { body: { usuario_id: user?.id } },
        ),
      );
      if (resp.success) {
        alert('Tabla eliminada correctamente');
        await this.cargar();
      } else {
        alert(resp.message || 'Error al eliminar tabla');
      }
    } catch (err) {
      alert(errorMessage(err, 'Error al eliminar tabla'));
    }
  }
}
