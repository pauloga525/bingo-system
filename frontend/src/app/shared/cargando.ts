// Overlay de pantalla completa mientras hay peticiones al API en curso.
import { Component, inject } from '@angular/core';

import { LoadingService } from '../core/loading';

@Component({
  selector: 'app-cargando',
  template: `
    @if (loading.activo()) {
      <div
        class="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 backdrop-blur-[1px] cursor-wait"
        role="alert"
        aria-live="assertive"
        aria-busy="true"
      >
        <div
          class="flex flex-col items-center gap-4 rounded-2xl bg-white dark:bg-gray-900 px-8 py-6 shadow-2xl border border-gray-200 dark:border-gray-700"
        >
          <div
            class="h-12 w-12 rounded-full border-4 border-blue-200 border-t-blue-600 animate-spin"
          ></div>
          <p class="text-gray-800 dark:text-gray-100 font-medium">{{ loading.mensaje() }}</p>
        </div>
      </div>
    }
  `,
})
export class Cargando {
  protected readonly loading = inject(LoadingService);
}
