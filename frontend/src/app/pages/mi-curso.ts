// Curso del animador conectado: lista de sus alumnos con alta, edición y baja.
// El curso lo fija el servidor; el animador no puede mover alumnos a otro curso.
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { Edit, LucideAngularModule, Plus, Search, Trash2 } from 'lucide-angular';
import { firstValueFrom } from 'rxjs';

import { errorMessage } from '../core/http';
import { CrudField, CrudForm, CrudValues } from '../shared/crud-form';

interface Alumno {
  _id: string;
  primer_apellido: string;
  segundo_apellido: string;
  nombre: string;
  cedula: string;
  correo: string;
}

interface MiCursoResponse {
  curso: { nombre: string };
  estudiantes: Alumno[];
  total: number;
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
];
const HEADERS = ['#', 'Cédula', 'Apellidos y nombres', 'Correo', ''];

@Component({
  selector: 'app-mi-curso',
  imports: [LucideAngularModule, CrudForm],
  template: `
    <div class="p-6 max-w-5xl mx-auto">
      @if (sinCurso()) {
        <div
          class="bg-amber-50 dark:bg-amber-900/30 border border-amber-300 dark:border-amber-700 text-amber-800 dark:text-amber-200 rounded-xl p-4"
        >
          {{ sinCurso() }}
        </div>
      } @else {
        <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div>
            <h1 class="text-2xl font-bold text-gray-900 dark:text-white">Mi curso</h1>
            <p class="text-sm text-gray-600 dark:text-gray-400">
              {{ curso() }} · {{ alumnos().length }} alumnos
            </p>
          </div>
          <button
            type="button"
            (click)="editing.set({})"
            class="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg"
          >
            <lucide-icon [img]="PlusIcon" [size]="16" /> Nuevo alumno
          </button>
        </div>

        <form (submit)="$event.preventDefault(); cargar()" class="flex gap-2 mb-4">
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
                @for (e of alumnos(); track e._id; let i = $index) {
                  <tr class="border-t border-gray-200 dark:border-gray-700">
                    <td class="px-3 py-2 text-gray-500">{{ i + 1 }}</td>
                    <td class="px-3 py-2">{{ e.cedula }}</td>
                    <td class="px-3 py-2">
                      {{ e.primer_apellido }} {{ e.segundo_apellido }} {{ e.nombre }}
                    </td>
                    <td class="px-3 py-2">
                      @if (e.correo) {
                        {{ e.correo }}
                      } @else {
                        <span class="text-gray-400">sin registrar</span>
                      }
                    </td>
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
                } @empty {
                  <tr>
                    <td [attr.colspan]="headers.length" class="px-3 py-4 text-center text-gray-500">
                      No hay alumnos para mostrar.
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        }
      }

      @if (editing(); as e) {
        <app-crud-form
          [title]="e['_id'] ? 'Editar alumno' : 'Nuevo alumno de ' + curso()"
          [fields]="fields"
          [initial]="e"
          [save]="guardar"
          (closed)="editing.set(null)"
        />
      }
    </div>
  `,
})
export class MiCurso implements OnInit {
  private readonly http = inject(HttpClient);
  protected readonly PlusIcon = Plus;
  protected readonly SearchIcon = Search;
  protected readonly EditIcon = Edit;
  protected readonly TrashIcon = Trash2;
  protected readonly fields = FIELDS;
  protected readonly headers = HEADERS;

  protected readonly curso = signal('');
  protected readonly alumnos = signal<Alumno[]>([]);
  protected readonly search = signal('');
  protected readonly loading = signal(true);
  protected readonly error = signal('');
  /** Mensaje cuando el animador no tiene curso asignado. */
  protected readonly sinCurso = signal('');
  protected readonly editing = signal<CrudValues | null>(null);

  ngOnInit(): void {
    void this.cargar();
  }

  protected async cargar(): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try {
      const data = await firstValueFrom(
        this.http.get<MiCursoResponse>('/api/mi-curso', { params: { search: this.search() } }),
      );
      this.curso.set(data.curso.nombre);
      this.alumnos.set(data.estudiantes || []);
      this.sinCurso.set('');
    } catch (err) {
      const msg = errorMessage(err, 'Error al cargar los alumnos del curso.');
      if ((err as { status?: number }).status === 404) this.sinCurso.set(msg);
      else this.error.set(msg);
    } finally {
      this.loading.set(false);
    }
  }

  protected readonly guardar = async (values: CrudValues): Promise<void> => {
    const body = Object.fromEntries(FIELDS.map((f) => [f.name, values[f.name] ?? '']));
    const id = values['_id'] ? String(values['_id']) : '';
    await firstValueFrom(
      id
        ? this.http.put(`/api/mi-curso/estudiantes/${id}`, body)
        : this.http.post('/api/mi-curso/estudiantes', body),
    );
    await this.cargar();
  };

  protected async eliminar(e: Alumno): Promise<void> {
    const nombre = `${e.primer_apellido} ${e.segundo_apellido} ${e.nombre}`.trim();
    if (!confirm(`¿Eliminar a ${nombre} de la lista del curso?`)) return;
    try {
      await firstValueFrom(this.http.delete(`/api/mi-curso/estudiantes/${e._id}`));
      await this.cargar();
    } catch (err) {
      alert(errorMessage(err, 'No se pudo eliminar.'));
    }
  }
}
