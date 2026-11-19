// Vista de un cartón (tabla) individual.
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { ArrowLeft, Loader, LucideAngularModule, Star } from 'lucide-angular';
import { firstValueFrom } from 'rxjs';

import { LETRAS, Tabla, cellText, toMatrix } from '../core/tablas';

interface TablaDetalle extends Tabla {
  participante?: { nombre?: string; apellido?: string } | null;
}

@Component({
  selector: 'app-carton-view',
  imports: [RouterLink, LucideAngularModule],
  template: `
    <div class="min-h-[80vh] flex items-center justify-center p-4">
      @if (loading()) {
        <lucide-icon [img]="LoaderIcon" [size]="32" class="animate-spin text-blue-500" />
      } @else if (!tabla()) {
        <p class="text-gray-700 dark:text-gray-200">Cartón no encontrado</p>
      } @else {
        <div
          class="w-full max-w-sm text-center bg-white dark:bg-gray-900 rounded-xl p-6 border border-gray-200 dark:border-gray-700 shadow-lg"
        >
          <h1 class="text-2xl font-bold text-gray-900 dark:text-white mb-1">
            Cartón {{ titulo() }}
          </h1>
          <p class="text-gray-600 dark:text-gray-300 mb-8">Serial: {{ tabla()?.serial }}</p>

          <div class="grid grid-cols-5 gap-3 justify-items-center">
            @for (l of letras; track l) {
              <div class="text-2xl font-bold text-blue-600">{{ l }}</div>
            }
            @for (row of matriz(); track $index) {
              @for (value of row; track $index) {
                @if (cellText(value) === 'LIBRE') {
                  <div
                    class="h-14 w-14 rounded-full flex justify-center items-center bg-blue-600 text-white border-2 border-gray-300"
                  >
                    <lucide-icon [img]="StarIcon" [size]="28" />
                  </div>
                } @else {
                  <div
                    class="h-14 w-14 rounded-lg flex justify-center items-center font-bold text-lg border-2 border-gray-300 dark:border-gray-600 bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-200"
                  >
                    {{ value }}
                  </div>
                }
              }
            }
          </div>

          <div
            class="mt-8 p-4 rounded-lg"
            [class]="
              tabla()?.won
                ? 'bg-yellow-300 text-yellow-900'
                : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-100'
            "
          >
            <h3 class="text-xl font-bold">{{ tabla()?.won ? '¡GANADORA!' : 'SIN PREMIO' }}</h3>
            <p class="text-sm">
              {{ tabla()?.won ? 'Esta tabla tiene un premio.' : 'Esta tabla no tiene premio.' }}
            </p>
          </div>

          <a
            routerLink="/admin/cartones"
            class="inline-flex items-center gap-2 bg-blue-600 text-white px-5 py-3 rounded-lg mt-8 hover:bg-blue-700"
          >
            <lucide-icon [img]="ArrowLeftIcon" [size]="16" /> Volver al buscador
          </a>
        </div>
      }
    </div>
  `,
})
export class CartonView implements OnInit {
  private readonly http = inject(HttpClient);
  protected readonly ArrowLeftIcon = ArrowLeft;
  protected readonly LoaderIcon = Loader;
  protected readonly StarIcon = Star;
  protected readonly letras = LETRAS;
  protected readonly cellText = cellText;

  /** Parámetro de ruta :cartonId. */
  readonly cartonId = input.required<string>();

  protected readonly tabla = signal<TablaDetalle | null>(null);
  protected readonly loading = signal(true);
  protected readonly matriz = computed(() => toMatrix(this.tabla()?.matrix));
  protected readonly titulo = computed(() => {
    const p = this.tabla()?.participante;
    return p ? `de ${p.nombre || ''} ${p.apellido || ''}`.trim() : 'Sin asignar';
  });

  async ngOnInit(): Promise<void> {
    try {
      const resp = await firstValueFrom(
        this.http.get<{ success: boolean; tabla?: TablaDetalle }>(`/api/tablas/${this.cartonId()}`),
      );
      if (resp.success && resp.tabla) this.tabla.set(resp.tabla);
    } catch (err) {
      console.error('Error al cargar tabla:', err);
    } finally {
      this.loading.set(false);
    }
  }
}
