// Panel: buscar participante por cédula y descargar sus tablas en PDF.
import { HttpClient } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { errorMessage } from '../core/http';
import { Tabla, descargarTablasPDF } from '../core/tablas';

interface ParticipanteDetalle {
  nombre?: string;
  apellido?: string;
  cedula?: string;
  nivelCurso?: string;
  paralelo?: string;
  tablas?: Tabla[];
}

@Component({
  selector: 'app-buscar-participante',
  template: `
    <div class="p-6 max-w-4xl mx-auto text-gray-900 dark:text-gray-100">
      <h1 class="text-2xl font-bold mb-4">Buscar participante por cédula y descargar tablas</h1>

      <form (submit)="buscar($event)" class="flex flex-wrap gap-2 items-center mb-4">
        <input
          type="text"
          placeholder="Cédula"
          [value]="cedula()"
          (input)="cedula.set($any($event.target).value)"
          class="border rounded px-3 py-2 w-64 dark:bg-gray-800"
        />
        <button type="submit" class="bg-blue-600 text-white px-4 py-2 rounded">Buscar</button>
        <button
          type="button"
          (click)="limpiar()"
          class="ml-2 text-sm text-gray-600 dark:text-gray-300"
        >
          Limpiar
        </button>
      </form>

      @if (loading()) {
        <p>Cargando...</p>
      }
      @if (error()) {
        <p class="text-red-600">{{ error() }}</p>
      }

      @if (participante(); as p) {
        <div class="mt-4 p-4 border rounded mb-4 space-y-1">
          <p><strong>Nombre:</strong> {{ p.nombre }} {{ p.apellido }}</p>
          <p><strong>Cédula:</strong> {{ p.cedula }}</p>
          <p><strong>Nivel/Curso:</strong> {{ p.nivelCurso }} {{ p.paralelo }}</p>
          <p><strong>Tablas asignadas:</strong> {{ p.tablas?.length || 0 }}</p>
        </div>
        <button
          type="button"
          (click)="descargar(p)"
          [disabled]="!p.tablas?.length"
          class="px-4 py-2 rounded text-white bg-green-600 hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
        >
          Descargar PDF de tablas
        </button>
      }
    </div>
  `,
})
export class BuscarParticipante {
  private readonly http = inject(HttpClient);

  protected readonly cedula = signal('');
  protected readonly loading = signal(false);
  protected readonly error = signal('');
  protected readonly participante = signal<ParticipanteDetalle | null>(null);

  protected limpiar(): void {
    this.cedula.set('');
    this.participante.set(null);
    this.error.set('');
  }

  protected async buscar(event: Event): Promise<void> {
    event.preventDefault();
    const cedula = this.cedula().trim();
    if (!cedula) {
      this.error.set('Ingrese una cédula');
      return;
    }
    this.loading.set(true);
    this.error.set('');
    this.participante.set(null);
    try {
      const resp = await firstValueFrom(
        this.http.get<{ success: boolean; message?: string; participante?: ParticipanteDetalle }>(
          `/api/participante/cedula/${encodeURIComponent(cedula)}`,
        ),
      );
      if (resp.success && resp.participante) this.participante.set(resp.participante);
      else this.error.set(resp.message || 'No se encontró participante');
    } catch (err) {
      this.error.set(errorMessage(err, 'Error al consultar'));
    } finally {
      this.loading.set(false);
    }
  }

  protected descargar(p: ParticipanteDetalle): void {
    const nombre = `${p.nombre || ''} ${p.apellido || ''}`.trim();
    descargarTablasPDF(
      p.tablas || [],
      `Bingo UETS - ${nombre}`,
      `tablas_${p.cedula || 'participante'}.pdf`,
    );
  }
}
