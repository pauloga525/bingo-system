// CRUD de estudiantes (solo admin). Con el correo el estudiante puede ver sus tablas.
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import {
  Edit,
  FileSpreadsheet,
  FilterX,
  LucideAngularModule,
  Plus,
  Search,
  Trash2,
} from 'lucide-angular';
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
const HEADERS = [
  'Cédula',
  'Apellidos y nombres',
  'Correo',
  'Nivel educativo',
  'Curso',
  'Especialidad / subnivel',
  'Paralelo',
  '',
];
const PER_PAGE = 25;

/** Curso (paralelo) con alumnos, de /api/cursos: alimenta los filtros en cascada. */
interface CursoOpcion {
  curso: string;
  especialidad: string;
  nivel: number;
  paralelo: string;
  estudiantes: number;
}

interface Filtros {
  curso: string;
  especialidad: string;
  nivel: string;
  paralelo: string;
  correo: '' | 'con' | 'sin';
}

const SIN_FILTROS: Filtros = { curso: '', especialidad: '', nivel: '', paralelo: '', correo: '' };
const SELECT =
  'border border-gray-300 dark:border-gray-600 dark:bg-gray-700 dark:text-white rounded-lg px-3 py-2 text-sm';

/** "BACHILLERATO" -> "Bachillerato"; "Educación General Básica" -> "EGB". */
export const nivelEducativo = (curso: string): string =>
  curso === 'BACHILLERATO' ? 'Bachillerato' : curso === 'Educación General Básica' ? 'EGB' : curso;

const unicos = <T>(valores: T[]): T[] => [...new Set(valores)];

@Component({
  selector: 'app-estudiantes-admin',
  imports: [LucideAngularModule, CrudForm, RouterLink],
  template: `
    <div class="p-6 max-w-6xl mx-auto">
      <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
        <div>
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white">Estudiantes</h1>
          <p class="text-sm text-gray-600 dark:text-gray-400">{{ total() }} encontrados</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <a
            routerLink="/admin/mantenimiento"
            title="Reemplazar todos los estudiantes con el Excel de secretaría"
            class="flex items-center gap-2 bg-gray-200 dark:bg-gray-700 dark:text-white px-4 py-2 rounded-lg"
          >
            <lucide-icon [img]="ExcelIcon" [size]="16" /> Importar Excel
          </a>
          <button
            type="button"
            (click)="editing.set({})"
            class="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg"
          >
            <lucide-icon [img]="PlusIcon" [size]="16" /> Nuevo estudiante
          </button>
        </div>
      </div>

      <form (submit)="$event.preventDefault(); buscar()" class="flex flex-wrap gap-2 mb-3">
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

      <!-- Filtros en cascada: cada lista muestra solo lo que existe con los filtros anteriores. -->
      <div class="flex flex-wrap items-center gap-2 mb-4">
        <select
          aria-label="Nivel educativo"
          [value]="filtros().curso"
          (change)="filtrar('curso', $any($event.target).value)"
          [class]="select"
        >
          <option value="">Nivel educativo: todos</option>
          @for (c of opcionesCurso(); track c) {
            <option [value]="c">{{ nivelEducativo(c) }}</option>
          }
        </select>
        <select
          aria-label="Curso"
          [value]="filtros().nivel"
          (change)="filtrar('nivel', $any($event.target).value)"
          [class]="select"
        >
          <option value="">Curso: todos</option>
          @for (n of opcionesNivel(); track n) {
            <option [value]="n">{{ n }}.º</option>
          }
        </select>
        <select
          aria-label="Especialidad"
          [value]="filtros().especialidad"
          (change)="filtrar('especialidad', $any($event.target).value)"
          [class]="select"
        >
          <option value="">Especialidad / subnivel: todas</option>
          @for (e of opcionesEspecialidad(); track e) {
            <option [value]="e">{{ e }}</option>
          }
        </select>
        <select
          aria-label="Paralelo"
          [value]="filtros().paralelo"
          (change)="filtrar('paralelo', $any($event.target).value)"
          [class]="select"
        >
          <option value="">Paralelo: todos</option>
          @for (p of opcionesParalelo(); track p) {
            <option [value]="p">{{ p }}</option>
          }
        </select>
        <select
          aria-label="Correo"
          [value]="filtros().correo"
          (change)="filtrar('correo', $any($event.target).value)"
          [class]="select"
        >
          <option value="">Correo: todos</option>
          <option value="con">Con correo</option>
          <option value="sin">Sin correo</option>
        </select>
        @if (hayFiltros()) {
          <button
            type="button"
            (click)="limpiar()"
            class="flex items-center gap-1 text-sm text-blue-600 hover:underline"
          >
            <lucide-icon [img]="FilterXIcon" [size]="16" /> Limpiar filtros
          </button>
        }
      </div>

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
                  <td class="px-3 py-2 whitespace-nowrap">
                    <span
                      class="text-xs px-2 py-0.5 rounded"
                      [class]="
                        e.curso === 'BACHILLERATO'
                          ? 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900 dark:text-indigo-200'
                          : 'bg-teal-100 text-teal-800 dark:bg-teal-900 dark:text-teal-200'
                      "
                      >{{ nivelEducativo(e.curso) }}</span
                    >
                  </td>
                  <td class="px-3 py-2 whitespace-nowrap">{{ e.nivel }}.º</td>
                  <td class="px-3 py-2">{{ e.especialidad || '—' }}</td>
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
              } @empty {
                <tr>
                  <td [attr.colspan]="headers.length" class="px-3 py-4 text-center text-gray-500">
                    No hay estudiantes con esos filtros.
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
  protected readonly ExcelIcon = FileSpreadsheet;
  protected readonly SearchIcon = Search;
  protected readonly EditIcon = Edit;
  protected readonly TrashIcon = Trash2;
  protected readonly fields = FIELDS;
  protected readonly headers = HEADERS;
  protected readonly FilterXIcon = FilterX;
  protected readonly select = SELECT;
  protected readonly nivelEducativo = nivelEducativo;

  private readonly cursos = signal<CursoOpcion[]>([]);
  protected readonly filtros = signal<Filtros>({ ...SIN_FILTROS });
  protected readonly hayFiltros = computed(() =>
    Object.values(this.filtros()).some((v) => v !== ''),
  );
  /** Cursos que cumplen los filtros elegidos, sin contar ``campo`` (para sus opciones). */
  private cursosSin(campo: keyof Filtros): CursoOpcion[] {
    const f = this.filtros();
    return this.cursos().filter(
      (c) =>
        (campo === 'curso' || !f.curso || c.curso === f.curso) &&
        (campo === 'nivel' || !f.nivel || String(c.nivel) === f.nivel) &&
        (campo === 'especialidad' || !f.especialidad || c.especialidad === f.especialidad) &&
        (campo === 'paralelo' || !f.paralelo || c.paralelo === f.paralelo),
    );
  }
  protected readonly opcionesCurso = computed(() =>
    unicos(this.cursosSin('curso').map((c) => c.curso)).sort(),
  );
  protected readonly opcionesNivel = computed(() =>
    unicos(this.cursosSin('nivel').map((c) => c.nivel)).sort((a, b) => a - b),
  );
  protected readonly opcionesEspecialidad = computed(() =>
    unicos(this.cursosSin('especialidad').map((c) => c.especialidad))
      .filter(Boolean)
      .sort(),
  );
  protected readonly opcionesParalelo = computed(() =>
    unicos(this.cursosSin('paralelo').map((c) => c.paralelo)).sort(),
  );

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
    void this.cargarCursos();
  }

  private async cargarCursos(): Promise<void> {
    try {
      const data = await firstValueFrom(this.http.get<{ cursos?: CursoOpcion[] }>('/api/cursos'));
      this.cursos.set(data.cursos || []);
    } catch {
      this.cursos.set([]); // sin opciones: la búsqueda por texto sigue funcionando
    }
  }

  protected filtrar(campo: keyof Filtros, valor: string): void {
    this.filtros.update((f) => ({ ...f, [campo]: valor }));
    this.irA(1);
  }

  protected limpiar(): void {
    this.filtros.set({ ...SIN_FILTROS });
    this.search.set('');
    this.query.set('');
    this.irA(1);
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
          params: {
            search: this.query(),
            page: this.page(),
            per_page: PER_PAGE,
            ...this.filtros(),
          },
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
