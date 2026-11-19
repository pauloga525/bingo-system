// CRUD de estudiantes (solo admin). Con el correo el estudiante puede ver sus tablas.
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { Edit, LucideAngularModule, Plus, Search, Trash2 } from 'lucide-angular';
import { firstValueFrom } from 'rxjs';

import { errorMessage } from '../core/http';
import { CrudField, CrudForm, CrudValues } from '../shared/crud-form';

interface Estudiante {
  _id: string;
  primer_apellido: string;
  segundo_apellido: string;
  nombre: string;
  cedula: string;
  correo: string;
  curso: string;
  especialidad: string;
  nivel: number | string;
  paralelo: string;
}

const FIELDS: CrudField[] = [
  { name: 'primer_apellido', label: 'Primer apellido', required: true },
  { name: 'segundo_apellido', label: 'Segundo apellido' },
  { name: 'nombre', label: 'Nombres', required: true, wide: true },
  { name: 'cedula', label: 'Cédula', required: true },
  {
    name: 'correo',
    label: 'Correo institucional',
    type: 'email',
    placeholder: 'nombre.apellido.est@uets.edu.ec',
  },
  { name: 'curso', label: 'Curso', required: true },
  { name: 'especialidad', label: 'Especialidad' },
  { name: 'nivel', label: 'Nivel', type: 'number', required: true },
  { name: 'paralelo', label: 'Paralelo', required: true },
];
const HEADERS = ['Cédula', 'Apellidos y nombres', 'Correo', 'Curso', 'Nivel', 'Paralelo', ''];
const PER_PAGE = 25;

@Component({
  selector: 'app-estudiantes-admin',
  imports: [LucideAngularModule, CrudForm],
  template: `
    <div class="p-6 max-w-6xl mx-auto">
      <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">Estudiantes</h1>
          <p class="text-sm text-gray-600 dark:text-gray-400">{{ total() }} encontrados</p>
        </div>
        <button
          type="button"
          (click)="editing.set({})"
          class="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg"
        >
          <lucide-icon [img]="PlusIcon" [size]="16" /> Nuevo estudiante
        </button>
      </div>

      <form (submit)="$event.preventDefault(); buscar()" class="flex gap-2 mb-4">
        <input
          [value]="search()"
          (input)="search.set($any($event.target).value)"
          placeholder="Buscar por cédula, apellido, nombre o correo"
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
              @for (e of estudiantes(); track e._id) {
                <tr class="border-t border-gray-200 dark:border-gray-700">
                  <td class="px-3 py-2">{{ e.cedula }}</td>
                  <td class="px-3 py-2">
                    {{ (e.primer_apellido + ' ' + e.segundo_apellido + ' ' + e.nombre).trim() }}
                  </td>
                  <td class="px-3 py-2">
                    @if (e.correo) {
                      {{ e.correo }}
                    } @else {
                      <span class="text-gray-400">—</span>
                    }
                  </td>
                  <td class="px-3 py-2">{{ e.curso }} {{ e.especialidad }}</td>
                  <td class="px-3 py-2">{{ e.nivel }}</td>
                  <td class="px-3 py-2">{{ e.paralelo }}</td>
                  <td class="px-3 py-2 whitespace-nowrap">
                    <button
                      type="button"
                      (click)="editing.set($any(e))"
                      class="text-blue-600 hover:text-blue-800 mr-3"
                      title="Editar"
                    >
                      <lucide-icon [img]="EditIcon" [size]="16" />
                    </button>
                    <button
                      type="button"
                      (click)="eliminar(e)"
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

      <div
        class="flex items-center justify-end gap-2 mt-4 text-sm text-gray-700 dark:text-gray-200"
      >
        <button
          type="button"
          [disabled]="page() <= 1"
          (click)="irA(page() - 1)"
          class="px-3 py-1 rounded bg-gray-200 dark:bg-gray-700 disabled:opacity-50"
        >
          Anterior
        </button>
        <span>Página {{ page() }} de {{ pages() }}</span>
        <button
          type="button"
          [disabled]="page() >= pages()"
          (click)="irA(page() + 1)"
          class="px-3 py-1 rounded bg-gray-200 dark:bg-gray-700 disabled:opacity-50"
        >
          Siguiente
        </button>
      </div>

      @if (editing(); as e) {
        <app-crud-form
          [title]="e['_id'] ? 'Editar estudiante' : 'Nuevo estudiante'"
          [fields]="fields"
          [initial]="e"
          [save]="guardar"
          (closed)="editing.set(null)"
        />
      }
    </div>
  `,
})
export class EstudiantesAdmin implements OnInit {
  private readonly http = inject(HttpClient);
  protected readonly PlusIcon = Plus;
  protected readonly SearchIcon = Search;
  protected readonly EditIcon = Edit;
  protected readonly TrashIcon = Trash2;
  protected readonly fields = FIELDS;
  protected readonly headers = HEADERS;

  protected readonly estudiantes = signal<Estudiante[]>([]);
  protected readonly total = signal(0);
  protected readonly page = signal(1);
  protected readonly search = signal('');
  private readonly query = signal('');
  protected readonly loading = signal(true);
  protected readonly error = signal('');
  protected readonly editing = signal<CrudValues | null>(null);
  protected readonly pages = computed(() => Math.max(1, Math.ceil(this.total() / PER_PAGE)));

  ngOnInit(): void {
    void this.cargar();
  }

  protected buscar(): void {
    this.query.set(this.search().trim());
    this.irA(1);
  }

  protected irA(page: number): void {
    this.page.set(page);
    void this.cargar();
  }

  private async cargar(): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try {
      const data = await firstValueFrom(
        this.http.get<{ estudiantes?: Estudiante[]; total?: number }>('/api/estudiantes', {
          params: { search: this.query(), page: this.page(), per_page: PER_PAGE },
        }),
      );
      this.estudiantes.set(data.estudiantes || []);
      this.total.set(data.total || 0);
    } catch (err) {
      this.error.set(errorMessage(err, 'Error al cargar estudiantes.'));
    } finally {
      this.loading.set(false);
    }
  }

  protected readonly guardar = async (values: CrudValues): Promise<void> => {
    const { _id, ...body } = values;
    const payload = { ...body, nivel: Number(body['nivel']) };
    if (_id) await firstValueFrom(this.http.put(`/api/estudiantes/${String(_id)}`, payload));
    else await firstValueFrom(this.http.post('/api/estudiantes', payload));
    await this.cargar();
  };

  protected async eliminar(e: Estudiante): Promise<void> {
    if (!confirm(`¿Eliminar al estudiante ${e.nombre} ${e.primer_apellido}?`)) return;
    try {
      await firstValueFrom(this.http.delete(`/api/estudiantes/${e._id}`));
      await this.cargar();
    } catch (err) {
      alert(errorMessage(err, 'No se pudo eliminar.'));
    }
  }
}
