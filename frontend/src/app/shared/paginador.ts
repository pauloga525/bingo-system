// Controles de paginación: « Anterior · Página X de N · Siguiente » y total de registros.
import { Component, computed, input, output } from '@angular/core';

@Component({
  selector: 'app-paginador',
  template: `
    @if (total() > 0) {
      <div
        class="flex flex-wrap items-center justify-between gap-3 py-3 text-sm text-gray-600 dark:text-gray-300"
      >
        <span>
          {{ desde() }}–{{ hasta() }} de <strong>{{ total() }}</strong>
        </span>
        <div class="flex items-center gap-2">
          <button
            type="button"
            (click)="ir(1)"
            [disabled]="pagina() <= 1"
            [class]="boton"
            aria-label="Primera página"
          >
            «
          </button>
          <button
            type="button"
            (click)="ir(pagina() - 1)"
            [disabled]="pagina() <= 1"
            [class]="boton"
          >
            Anterior
          </button>
          <span>Página {{ pagina() }} de {{ paginas() }}</span>
          <button
            type="button"
            (click)="ir(pagina() + 1)"
            [disabled]="pagina() >= paginas()"
            [class]="boton"
          >
            Siguiente
          </button>
          <button
            type="button"
            (click)="ir(paginas())"
            [disabled]="pagina() >= paginas()"
            [class]="boton"
            aria-label="Última página"
          >
            »
          </button>
        </div>
      </div>
    }
  `,
})
export class Paginador {
  readonly pagina = input.required<number>();
  readonly porPagina = input.required<number>();
  readonly total = input.required<number>();
  readonly cambiar = output<number>();

  protected readonly boton =
    'px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed';
  protected readonly paginas = computed(() =>
    Math.max(1, Math.ceil(this.total() / this.porPagina())),
  );
  protected readonly desde = computed(() => (this.pagina() - 1) * this.porPagina() + 1);
  protected readonly hasta = computed(() =>
    Math.min(this.pagina() * this.porPagina(), this.total()),
  );

  protected ir(p: number): void {
    const destino = Math.min(Math.max(p, 1), this.paginas());
    if (destino !== this.pagina()) this.cambiar.emit(destino);
  }
}
