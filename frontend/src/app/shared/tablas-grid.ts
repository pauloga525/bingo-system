// Lista de tablas (tarjetas 5x5) con botón para descargarlas todas en PDF.
import { Component, input } from '@angular/core';
import { Download, LucideAngularModule } from 'lucide-angular';

import { LETRAS, Tabla, cellText, descargarTablasPDF, toMatrix } from '../core/tablas';

@Component({
  selector: 'app-tablas-grid',
  imports: [LucideAngularModule],
  template: `
    @if (!tablas().length) {
      <p class="text-gray-600 dark:text-gray-300">No hay tablas asignadas.</p>
    } @else {
      <div class="flex items-center justify-between mb-4">
        <p class="text-gray-700 dark:text-gray-200">
          <strong>{{ tablas().length }}</strong> {{ tablas().length === 1 ? 'tabla' : 'tablas' }}
        </p>
        <button
          type="button"
          (click)="descargar()"
          class="flex items-center gap-2 bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg"
        >
          <lucide-icon [img]="DownloadIcon" [size]="16" /> Descargar PDF
        </button>
      </div>
      <div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        @for (tabla of tablas(); track tabla.serial) {
          <div
            class="bg-white dark:bg-gray-800 rounded-xl shadow p-3 border border-gray-200 dark:border-gray-700"
          >
            <div class="flex items-center justify-between mb-2">
              <span class="font-semibold text-gray-800 dark:text-gray-100">{{ tabla.serial }}</span>
              @if (tabla.won) {
                <span class="text-xs bg-yellow-400 text-gray-900 px-2 py-0.5 rounded"
                  >Ganadora</span
                >
              }
            </div>
            <div class="grid grid-cols-5 gap-1 text-center">
              @for (l of letras; track l) {
                <div class="bg-blue-600 text-white font-bold rounded py-1">{{ l }}</div>
              }
              @for (row of matrix(tabla); track $index) {
                @for (value of row; track $index) {
                  @let texto = cellText(value);
                  <div
                    class="border rounded py-2 font-semibold"
                    [class]="
                      texto === 'LIBRE'
                        ? 'text-xs bg-gray-100 dark:bg-gray-700 text-gray-500'
                        : 'text-gray-900 dark:text-gray-100 border-gray-300 dark:border-gray-600'
                    "
                  >
                    {{ texto }}
                  </div>
                }
              }
            </div>
          </div>
        }
      </div>
    }
  `,
})
export class TablasGrid {
  readonly tablas = input<Tabla[]>([]);
  readonly titulo = input('Bingo UETS');
  readonly archivo = input('tablas.pdf');

  protected readonly DownloadIcon = Download;
  protected readonly letras = LETRAS;
  protected readonly matrix = (t: Tabla) => toMatrix(t.matrix);
  protected readonly cellText = cellText;

  protected descargar(): void {
    descargarTablasPDF(this.tablas(), this.titulo(), this.archivo());
  }
}
