// CRUD de animadores (solo admin). El correo es el que le permite iniciar sesión con Google.
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { Edit, LucideAngularModule, Plus, Search, Trash2 } from 'lucide-angular';
import { firstValueFrom } from 'rxjs';

import { errorMessage, onlyDigits } from '../core/http';
import { SessionService } from '../core/session';
import { CrudField, CrudForm, CrudValues } from '../shared/crud-form';

interface Animador {
  _id: string;
  nombre: string;
  correo: string;
  curso: string;
  especialidad: string;
  nivel: number | string;
  paralelo: string;
  usuario: string | null;
  usuario_id: string | null;
  reserva: { total: number; usadas: number; desde: string; hasta: string } | null;
}

const FIELDS: CrudField[] = [
  {
    name: 'nombre',
    label: 'Nombres completos',
    required: true,
    wide: true,
    placeholder: 'APELLIDOS NOMBRES',
  },
  {
    name: 'correo',
    label: 'Correo institucional',
    type: 'email',
    wide: true,
    placeholder: 'nombre@uets.edu.ec',
  },
  { name: 'curso', label: 'Curso', required: true, placeholder: 'EDUCACIÓN GENERAL BÁSICA' },
  { name: 'especialidad', label: 'Especialidad', required: true, placeholder: 'Básica Media' },
  { name: 'nivel', label: 'Nivel', type: 'number', required: true },
  { name: 'paralelo', label: 'Paralelo', required: true },
];

const HEADERS = [
  'Nombre',
  'Correo',
  'Curso',
  'Especialidad',
  'Nivel',
  'Paralelo',
  'Usuario',
  'Tablas',
  '',
];

@Component({
  selector: 'app-animadores-admin',
  imports: [LucideAngularModule, CrudForm],
  template: `
    <div class="p-6 max-w-6xl mx-auto">
      <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">Animadores</h1>
          <p class="text-sm text-gray-600 dark:text-gray-400">
            {{ animadores().length }} registrados · {{ conAcceso() }} con correo (pueden iniciar
            sesión)
          </p>
        </div>
        <button
          type="button"
          (click)="editing.set({})"
          class="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg"
        >
          <lucide-icon [img]="PlusIcon" [size]="16" /> Nuevo animador
        </button>
      </div>

      <form (submit)="$event.preventDefault(); cargar()" class="flex gap-2 mb-4">
        <input
          [value]="search()"
          (input)="search.set($any($event.target).value)"
          placeholder="Buscar por nombre, correo o curso"
          class="border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white rounded-lg px-3 py-2 w-80"
        />
        <button
          type="submit"
          class="flex items-center gap-1 bg-gray-200 dark:bg-gray-700 dark:text-white px-3 py-2 rounded-lg"
        >
          <lucide-icon [img]="SearchIcon" [size]="16" /> Buscar
        </button>
      </form>

      @if (error()) {
        <p class="text-red-600 mb-3">{{ error() }}</p>
      }
      @if (loading()) {
        <p class="text-gray-600">Cargando...</p>
      } @else {
        <div class="overflow-x-auto bg-white dark:bg-gray-800 rounded-xl shadow">
          <table class="min-w-full text-sm">
            <thead class="bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200">
              <tr>
                @for (h of headers; track $index) {
                  <th class="text-left px-3 py-2">{{ h }}</th>
                }
              </tr>
            </thead>
            <tbody class="text-gray-800 dark:text-gray-100">
              @for (a of animadores(); track a._id) {
                <tr class="border-t border-gray-200 dark:border-gray-700">
                  <td class="px-3 py-2">{{ a.nombre }}</td>
                  <td class="px-3 py-2">
                    @if (a.correo) {
                      {{ a.correo }}
                    } @else {
                      <span class="text-gray-400">sin acceso</span>
                    }
                  </td>
                  <td class="px-3 py-2">{{ a.curso }}</td>
                  <td class="px-3 py-2">{{ a.especialidad }}</td>
                  <td class="px-3 py-2">{{ a.nivel }}</td>
                  <td class="px-3 py-2">{{ a.paralelo }}</td>
                  <td class="px-3 py-2">{{ a.usuario || '—' }}</td>
                  <td class="px-3 py-2 whitespace-nowrap">
                    @if (a.reserva; as r) {
                      <span [title]="'Usadas ' + r.usadas + ' de ' + r.total">
                        {{ r.hasta }} – {{ r.desde }} ({{ r.usadas }}/{{ r.total }})
                      </span>
                    } @else {
                      <button
                        type="button"
                        (click)="reservar(a)"
                        class="text-sm text-blue-600 hover:underline"
                      >
                        Reservar
                      </button>
                    }
                  </td>
                  <td class="px-3 py-2 whitespace-nowrap">
                    <button
                      type="button"
                      (click)="editing.set($any(a))"
                      class="text-blue-600 hover:text-blue-800 mr-3"
                      title="Editar"
                    >
                      <lucide-icon [img]="EditIcon" [size]="16" />
                    </button>
                    <button
                      type="button"
                      (click)="eliminar(a)"
                      class="text-red-600 hover:text-red-800"
                      title="Eliminar"
                    >
                      <lucide-icon [img]="TrashIcon" [size]="16" />
                    </button>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }

      @if (editing(); as e) {
        <app-crud-form
          [title]="e['_id'] ? 'Editar animador' : 'Nuevo animador'"
          [fields]="fields"
          [initial]="e"
          [save]="guardar"
          (closed)="editing.set(null)"
        />
      }
    </div>
  `,
})
export class AnimadoresAdmin implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly session = inject(SessionService);
  protected readonly PlusIcon = Plus;
  protected readonly SearchIcon = Search;
  protected readonly EditIcon = Edit;
  protected readonly TrashIcon = Trash2;
  protected readonly fields = FIELDS;
  protected readonly headers = HEADERS;

  protected readonly animadores = signal<Animador[]>([]);
  protected readonly search = signal('');
  protected readonly loading = signal(true);
  protected readonly error = signal('');
  /** null = cerrado, {} = nuevo, {...} = editar */
  protected readonly editing = signal<CrudValues | null>(null);
  protected readonly conAcceso = computed(() => this.animadores().filter((a) => a.correo).length);

  ngOnInit(): void {
    void this.cargar();
  }

  protected async cargar(): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try {
      const data = await firstValueFrom(
        this.http.get<{ animadores?: Animador[] }>('/api/animadores', {
          params: { search: this.search() },
        }),
      );
      this.animadores.set(data.animadores || []);
    } catch (err) {
      this.error.set(errorMessage(err, 'Error al cargar animadores.'));
    } finally {
      this.loading.set(false);
    }
  }

  protected readonly guardar = async (values: CrudValues): Promise<void> => {
    const { _id, usuario, usuario_id, reserva, ...body } = values;
    void usuario;
    void usuario_id;
    void reserva;
    const payload = { ...body, nivel: Number(body['nivel']) };
    if (_id) await firstValueFrom(this.http.put(`/api/animadores/${String(_id)}`, payload));
    else await firstValueFrom(this.http.post('/api/animadores', payload));
    await this.cargar();
  };

  protected async eliminar(a: Animador): Promise<void> {
    if (!confirm(`¿Eliminar al animador ${a.nombre}?`)) return;
    try {
      await firstValueFrom(this.http.delete(`/api/animadores/${a._id}`));
      await this.cargar();
    } catch (err) {
      alert(errorMessage(err, 'No se pudo eliminar.'));
    }
  }

  /** Reserva un bloque de tablas libres a la cuenta del animador (solo admin). */
  protected async reservar(a: Animador): Promise<void> {
    if (!a.usuario_id) {
      alert('Este animador aún no tiene cuenta. Edítelo y guarde para crearla.');
      return;
    }
    const cantidad = parseInt(onlyDigits(prompt(`¿Cuántas tablas reservar para ${a.nombre}?`)), 10);
    if (!cantidad) return;
    try {
      const data = await firstValueFrom(
        this.http.post<{ from: string; to: string }>(`/api/users/${a.usuario_id}/assign_tables`, {
          totalTables: cantidad,
          requesting_user_id: this.session.user()?.id,
        }),
      );
      alert(`Tablas reservadas: ${data.from} a ${data.to}`);
      await this.cargar();
    } catch (err) {
      alert(errorMessage(err, 'No se pudo reservar.'));
    }
  }
}
