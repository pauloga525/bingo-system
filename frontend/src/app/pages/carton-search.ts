// Buscador de cartones (tablas) por serial o participante.
import { HttpClient } from '@angular/common/http';
import { Component, DestroyRef, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Award, Eye, Loader, LucideAngularModule, Search, X } from 'lucide-angular';
import { firstValueFrom } from 'rxjs';

import { Tabla } from '../core/tablas';

interface TablaConParticipante extends Tabla {
  timestamp?: number;
  participante?: {
    nombre?: string;
    apellido?: string;
    nivelCurso?: string;
    paralelo?: string;
  } | null;
}

const TH = 'px-6 py-3 text-left text-xs font-semibold text-gray-500';

@Component({
  selector: 'app-carton-search',
  imports: [RouterLink, LucideAngularModule],
  template: `
    <div class="p-6 lg:p-10">
      <h1 class="text-3xl font-bold text-gray-900 dark:text-white mb-1">Buscador de Cartones</h1>
      <p class="text-gray-600 dark:text-gray-300 mb-8">Busca y visualiza los cartones de bingo.</p>

      <div class="relative mb-6">
        <lucide-icon
          [img]="SearchIcon"
          [size]="16"
          class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
        />
        <input
          type="text"
          [value]="search()"
          (input)="cambiar($any($event.target).value)"
          placeholder="Buscar por ID del cartón o nombre del participante"
          class="w-full pl-10 pr-4 py-2.5 border rounded-lg focus:ring-2 focus:ring-blue-500 dark:bg-gray-900 dark:text-white"
        />
      </div>

      <div class="overflow-x-auto rounded-lg border bg-white dark:bg-gray-900">
        <table class="w-full">
          <thead class="bg-gray-50 dark:bg-gray-800">
            <tr>
              <th [class]="th">ID Cartón</th>
              <th [class]="th">Participante Asignado</th>
              <th [class]="th">Nivel</th>
              <th [class]="th">Paralelo</th>
              <th [class]="th">Fecha de Creación</th>
              <th [class]="th">Estado</th>
              <th class="px-6 py-3 text-right text-xs font-semibold text-gray-500">Acciones</th>
            </tr>
          </thead>
          <tbody>
            @if (loading()) {
              <tr>
                <td colspan="7" class="px-6 py-4 text-center">
                  <lucide-icon
                    [img]="LoaderIcon"
                    [size]="24"
                    class="animate-spin text-blue-500 inline-block"
                  />
                </td>
              </tr>
            } @else {
              @for (carton of tablas(); track carton._id) {
                <tr class="text-sm text-gray-900 dark:text-white">
                  <td class="px-6 py-4 font-medium">{{ carton.serial || '-' }}</td>
                  <td class="px-6 py-4">{{ nombre(carton) }}</td>
                  <td class="px-6 py-4">{{ carton.participante?.nivelCurso || '—' }}</td>
                  <td class="px-6 py-4">{{ carton.participante?.paralelo || '—' }}</td>
                  <td class="px-6 py-4">{{ fecha(carton) }}</td>
                  <td class="px-6 py-4">
                    <span
                      class="inline-flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium"
                      [class]="
                        carton.won
                          ? 'bg-green-100 text-green-500 dark:bg-green-800'
                          : 'bg-red-100 text-red-500 dark:bg-red-800'
                      "
                    >
                      <lucide-icon [img]="carton.won ? AwardIcon : XIcon" [size]="12" />
                      {{ carton.won ? 'Ganadora' : 'Sin Premio' }}
                    </span>
                  </td>
                  <td class="px-6 py-4 text-right">
                    <a
                      [routerLink]="['/admin/cartones', carton._id]"
                      class="inline-flex items-center gap-2 bg-blue-600 text-white px-4 py-2 rounded-lg font-bold hover:bg-blue-700"
                    >
                      <lucide-icon [img]="EyeIcon" [size]="16" /> Ver
                    </a>
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="7" class="px-6 py-4 text-center text-gray-500">
                    No se encontraron tablas
                  </td>
                </tr>
              }
            }
          </tbody>
        </table>
      </div>
    </div>
  `,
})
export class CartonSearch implements OnInit {
  private readonly http = inject(HttpClient);
  protected readonly AwardIcon = Award;
  protected readonly EyeIcon = Eye;
  protected readonly LoaderIcon = Loader;
  protected readonly SearchIcon = Search;
  protected readonly XIcon = X;
  protected readonly th = TH;

  protected readonly search = signal('');
  protected readonly tablas = signal<TablaConParticipante[]>([]);
  protected readonly loading = signal(true);
  private timer: ReturnType<typeof setTimeout> | undefined;

  constructor() {
    inject(DestroyRef).onDestroy(() => clearTimeout(this.timer));
  }

  ngOnInit(): void {
    void this.cargar('');
  }

  /** Busca 300 ms después de la última tecla. */
  protected cambiar(value: string): void {
    this.search.set(value);
    clearTimeout(this.timer);
    this.timer = setTimeout(() => void this.cargar(value), 300);
  }

  protected nombre(c: TablaConParticipante): string {
    const p = c.participante;
    return `${p?.nombre || ''} ${p?.apellido || ''}`.trim() || 'Sin asignar';
  }

  protected fecha(c: TablaConParticipante): string {
    return c.timestamp ? new Date(c.timestamp * 1000).toLocaleDateString() : '-';
  }

  private async cargar(term: string): Promise<void> {
    this.loading.set(true);
    try {
      const params: Record<string, string> = term ? { search: term } : {};
      const resp = await firstValueFrom(
        this.http.get<{ success: boolean; tablas?: TablaConParticipante[] }>('/api/tablas', {
          params,
        }),
      );
      // Ignora respuestas de búsquedas ya reemplazadas.
      if (resp.success && term === this.search()) this.tablas.set(resp.tablas || []);
    } catch (err) {
      console.error('Error al cargar tablas:', err);
    } finally {
      if (term === this.search()) this.loading.set(false);
    }
  }
}
