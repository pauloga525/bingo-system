// Registro del estudiante tras ingresar con Google: su correo (ya verificado por Google)
// se guarda en la BD solo si la cédula, nombres y apellidos coinciden con los de secretaría.
import { HttpClient } from '@angular/common/http';
import { Component, inject, input, output, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { errorMessage, onlyDigits } from '../core/http';
import { SesionResponse } from '../core/session';

const INPUT =
  'w-full mt-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-blue-500';

@Component({
  selector: 'app-registro-estudiante',
  template: `
    <form (submit)="enviar($event)" class="space-y-4">
      <div class="bg-blue-500/10 border border-blue-500/40 text-blue-200 p-3 rounded-lg text-sm">
        Es tu primer ingreso. Completa tus datos tal como constan en secretaría para enlazar tu
        correo con tus tablas.
      </div>
      <label class="block text-sm text-gray-300">
        Correo
        <input [value]="correo()" disabled [class]="inputClass + ' opacity-70'" />
      </label>
      <label class="block text-sm text-gray-300">
        Cédula
        <input
          [value]="cedula()"
          (input)="setCedula($event)"
          inputmode="numeric"
          maxlength="13"
          required
          placeholder="Número de cédula"
          [class]="inputClass"
        />
      </label>
      <label class="block text-sm text-gray-300">
        Nombres
        <input
          [value]="nombres()"
          (input)="nombres.set(valueOf($event))"
          required
          placeholder="Tus nombres"
          [class]="inputClass"
        />
      </label>
      <label class="block text-sm text-gray-300">
        Apellidos
        <input
          [value]="apellidos()"
          (input)="apellidos.set(valueOf($event))"
          required
          placeholder="Primer y segundo apellido"
          [class]="inputClass"
        />
      </label>
      @if (error()) {
        <div class="bg-red-500/20 border border-red-500 text-red-300 p-3 rounded-lg text-sm">
          {{ error() }}
        </div>
      }
      <div class="flex gap-2">
        <button
          type="button"
          (click)="cancelado.emit()"
          class="flex-1 py-3 rounded-lg bg-gray-800 text-gray-300 hover:bg-gray-700"
        >
          Cancelar
        </button>
        <button
          type="submit"
          [disabled]="enviando()"
          class="flex-1 py-3 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-medium disabled:opacity-60"
        >
          {{ enviando() ? 'Verificando...' : 'Registrarme' }}
        </button>
      </div>
    </form>
  `,
})
export class RegistroEstudiante {
  private readonly http = inject(HttpClient);

  readonly correo = input.required<string>();
  readonly registroToken = input.required<string>();
  readonly registrado = output<SesionResponse>();
  readonly cancelado = output<void>();

  protected readonly inputClass = INPUT;
  protected readonly cedula = signal('');
  protected readonly nombres = signal('');
  protected readonly apellidos = signal('');
  protected readonly error = signal('');
  protected readonly enviando = signal(false);

  protected valueOf(event: Event): string {
    return (event.target as HTMLInputElement).value;
  }

  protected setCedula(event: Event): void {
    const el = event.target as HTMLInputElement;
    el.value = onlyDigits(el.value);
    this.cedula.set(el.value);
  }

  protected async enviar(event: Event): Promise<void> {
    event.preventDefault();
    this.error.set('');
    this.enviando.set(true);
    try {
      const data = await firstValueFrom(
        this.http.post<SesionResponse>('/api/auth/registro', {
          registro_token: this.registroToken(),
          cedula: this.cedula(),
          nombres: this.nombres(),
          apellidos: this.apellidos(),
        }),
      );
      this.registrado.emit(data);
    } catch (err) {
      this.error.set(errorMessage(err, 'No se pudo completar el registro.'));
    } finally {
      this.enviando.set(false);
    }
  }
}
