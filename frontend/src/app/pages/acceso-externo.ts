// Acceso del público general (externo): cédula + correo de la compra → código por correo → sus tablas.
// Reemplaza a la consulta libre por cédula: sin el código nadie ve las tablas de otra persona.
import { HttpClient } from '@angular/common/http';
import { Component, inject, output, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { errorMessage } from '../core/http';
import { SesionResponse } from '../core/session';

const INPUT =
  'w-full p-3 rounded-lg bg-gray-900 border border-gray-700 text-white placeholder-gray-500';

@Component({
  selector: 'app-acceso-externo',
  template: `
    <div class="space-y-4">
      <p class="text-sm text-gray-400">
        Escribe la cédula y el correo que diste al comprar tus tablas. Te enviaremos un código para
        verlas.
      </p>
      @if (paso() === 'datos') {
        <form (submit)="pedirCodigo($event)" class="space-y-3">
          <input
            [value]="cedula()"
            (input)="cedula.set($any($event.target).value.trim())"
            inputmode="numeric"
            autocomplete="off"
            placeholder="Cédula"
            [class]="input"
          />
          <input
            type="email"
            [value]="correo()"
            (input)="correo.set($any($event.target).value.trim())"
            autocomplete="email"
            placeholder="Correo"
            [class]="input"
          />
          <button
            type="submit"
            [disabled]="ocupado() || !cedula() || !correo()"
            class="w-full bg-yellow-500 hover:bg-yellow-400 text-gray-900 font-bold py-3 rounded-lg disabled:opacity-50"
          >
            {{ ocupado() ? 'Enviando...' : 'Enviar código' }}
          </button>
        </form>
      } @else {
        <div
          class="bg-blue-500/20 border border-blue-500 text-blue-200 p-3 rounded-lg text-sm"
          role="status"
        >
          {{ aviso() }}
        </div>
        <form (submit)="verificar($event)" class="space-y-3">
          <input
            [value]="codigo()"
            (input)="codigo.set($any($event.target).value.replace(/\\D/g, '').slice(0, 6))"
            inputmode="numeric"
            autocomplete="one-time-code"
            maxlength="6"
            placeholder="Código de 6 dígitos"
            [class]="input + ' text-center text-2xl tracking-[0.5em]'"
          />
          <button
            type="submit"
            [disabled]="ocupado() || codigo().length !== 6"
            class="w-full bg-yellow-500 hover:bg-yellow-400 text-gray-900 font-bold py-3 rounded-lg disabled:opacity-50"
          >
            {{ ocupado() ? 'Verificando...' : 'Ver mis tablas' }}
          </button>
        </form>
        <div class="flex justify-between text-sm">
          <button type="button" (click)="volver()" class="text-gray-400 hover:underline">
            Cambiar datos
          </button>
          <button
            type="button"
            (click)="pedirCodigo()"
            [disabled]="ocupado()"
            class="text-blue-400 hover:underline disabled:opacity-50"
          >
            Reenviar código
          </button>
        </div>
      }
      @if (error()) {
        <div class="bg-red-500/20 border border-red-500 text-red-300 p-3 rounded-lg text-sm">
          {{ error() }}
        </div>
      }
    </div>
  `,
})
export class AccesoExterno {
  private readonly http = inject(HttpClient);
  readonly entrar = output<SesionResponse>();
  protected readonly input = INPUT;

  protected readonly paso = signal<'datos' | 'codigo'>('datos');
  protected readonly cedula = signal('');
  protected readonly correo = signal('');
  protected readonly codigo = signal('');
  protected readonly aviso = signal('');
  protected readonly error = signal('');
  protected readonly ocupado = signal(false);

  protected async pedirCodigo(event?: Event): Promise<void> {
    event?.preventDefault();
    if (this.ocupado()) return;
    this.ocupado.set(true);
    this.error.set('');
    try {
      const resp = await firstValueFrom(
        this.http.post<{ message: string }>('/api/auth/externo/codigo', {
          cedula: this.cedula(),
          correo: this.correo(),
        }),
      );
      this.aviso.set(resp.message);
      this.codigo.set('');
      this.paso.set('codigo');
    } catch (err) {
      this.error.set(errorMessage(err, 'No se pudo enviar el código. Intenta nuevamente.'));
    } finally {
      this.ocupado.set(false);
    }
  }

  protected async verificar(event: Event): Promise<void> {
    event.preventDefault();
    if (this.ocupado()) return;
    this.ocupado.set(true);
    this.error.set('');
    try {
      this.entrar.emit(
        await firstValueFrom(
          this.http.post<SesionResponse>('/api/auth/externo/verificar', {
            cedula: this.cedula(),
            correo: this.correo(),
            codigo: this.codigo(),
          }),
        ),
      );
    } catch (err) {
      this.error.set(errorMessage(err, 'No se pudo verificar el código.'));
    } finally {
      this.ocupado.set(false);
    }
  }

  protected volver(): void {
    this.paso.set('datos');
    this.error.set('');
  }
}
