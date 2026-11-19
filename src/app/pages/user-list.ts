// Participantes registrados por el usuario conectado, con su reserva de tablas.
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { Edit, Loader, LucideAngularModule, Plus, Search, Trash2 } from 'lucide-angular';
import { firstValueFrom } from 'rxjs';

import { errorMessage, onlyDigits } from '../core/http';
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
  totalTables?: number;
  usedTables?: number;
  fromSerial?: string;
  toSerial?: string;
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
            @if (isAdmin()) {
              <div class="flex items-center gap-2">
                <input
                  type="text"
                  inputmode="numeric"
                  [value]="reserveCount()"
                  (input)="setReserveCount($event)"
                  (keydown.enter)="$event.preventDefault(); reservar()"
                  placeholder="Cantidad tablas"
                  class="w-36 p-2 border rounded-lg"
                />
                @if (reserveError()) {
                  <div class="text-xs text-red-500">{{ reserveError() }}</div>
                }
                <button
                  type="button"
                  (click)="reservar()"
                  [disabled]="isReserving() || total() > 0"
                  class="px-3 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-60"
                >
                  {{ isReserving() ? 'Reservando...' : 'Reservar tablas' }}
                </button>
              </div>
            }

            @if (total() > 0) {
              <div class="text-sm text-gray-700 dark:text-gray-300">
                Reservadas: <strong>{{ total() }}</strong> | Usadas:
                <strong>{{ usuarioDoc()?.usedTables || 0 }}</strong>
                @if (usuarioDoc()?.fromSerial && usuarioDoc()?.toSerial) {
                  <span>
                    | Rango: {{ usuarioDoc()?.fromSerial }} → {{ usuarioDoc()?.toSerial }}</span
                  >
                }
              </div>
            }

            <button
              type="button"
              (click)="anadir()"
              [disabled]="total() === 0 && !isAdmin()"
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
  protected readonly reserveCount = signal('');
  protected readonly reserveError = signal('');
  protected readonly isReserving = signal(false);
  protected readonly loading = signal(true);
  protected readonly error = signal('');

  protected readonly total = computed(() => this.usuarioDoc()?.totalTables || 0);
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

  /** Recarga participantes y la reserva del usuario; devuelve la reserva. */
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
      return resp.usuario || {};
    } catch (err) {
      this.error.set(errorMessage(err, 'Error al conectar con el servidor'));
      return null;
    } finally {
      this.loading.set(false);
    }
  }

  protected setReserveCount(event: Event): void {
    const el = event.target as HTMLInputElement;
    el.value = onlyDigits(el.value);
    this.reserveCount.set(el.value);
    this.reserveError.set('');
  }

  /** Reserva tablas a la cuenta del admin conectado. Devuelve true si se reservaron. */
  protected async reservar(cantidadParam?: number): Promise<boolean> {
    this.reserveError.set('');
    const cantidad = cantidadParam ?? parseInt(this.reserveCount(), 10);
    if (!cantidad || cantidad <= 0) {
      this.reserveError.set('Ingrese una cantidad válida');
      return false;
    }
    this.isReserving.set(true);
    try {
      const resp = await firstValueFrom(
        this.http.post<{ success: boolean; message?: string; from: string; to: string }>(
          `/api/users/${this.userId}/assign_tables`,
          { totalTables: cantidad, requesting_user_id: this.userId },
        ),
      );
      if (!resp.success) {
        this.reserveError.set(resp.message || 'Error al reservar tablas');
        return false;
      }
      alert(`Tablas reservadas desde ${resp.from} hasta ${resp.to}`);
      this.reserveCount.set('');
      await this.cargar();
      return true;
    } catch (err) {
      this.reserveError.set(errorMessage(err, 'Error al reservar tablas'));
      return false;
    } finally {
      this.isReserving.set(false);
    }
  }

  protected async anadir(): Promise<void> {
    let doc = await this.cargar();
    if (!doc) return;
    let total = doc.totalTables || 0;

    if (total > 0 && total - (doc.usedTables || 0) <= 0) {
      alert('Ya no tienes tablas disponibles para asignar.');
      return;
    }
    if (total === 0) {
      if (!this.isAdmin()) {
        alert('No tienes tablas reservadas. Pide a un administrador que reserve tablas.');
        return;
      }
      // El admin puede reservar desde aquí: usa la cantidad escrita o la pide.
      let cantidad = parseInt(this.reserveCount(), 10);
      if (!cantidad) {
        const input = prompt('Ingrese la cantidad total de tablas a reservar (ej: 161):');
        if (input === null) return;
        cantidad = parseInt(onlyDigits(input), 10);
      }
      if (!(await this.reservar(cantidad || 0))) return;
      doc = this.usuarioDoc() || {};
      total = doc.totalTables || 0;
      if (!(total > 0 && total - (doc.usedTables || 0) > 0)) {
        alert('No se pudieron reservar las tablas o no hay tablas disponibles.');
        return;
      }
    }
    void this.router.navigate(['/admin/add-user'], {
      state: { fromSerial: doc.fromSerial, toSerial: doc.toSerial },
    });
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
