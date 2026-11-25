// Inicio de sesión: estudiantes y personal UETS con Google; público general con cédula + correo + código.
import { HttpClient } from '@angular/common/http';
import {
  AfterViewInit,
  Component,
  ElementRef,
  OnDestroy,
  inject,
  isDevMode,
  signal,
  viewChild,
} from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { API_BASE_URL, GOOGLE_CLIENT_ID } from '../core/config';
import { loadGoogleId } from '../core/google';
import { errorBody, errorMessage } from '../core/http';
import { SesionResponse, SessionService, homeFor } from '../core/session';
import { AccesoExterno } from './acceso-externo';
import { RegistroEstudiante } from './registro-estudiante';

interface RegistroPendiente {
  token: string;
  correo: string;
}

@Component({
  selector: 'app-login',
  imports: [RegistroEstudiante, AccesoExterno],
  template: `
    <div class="min-h-screen bg-gray-900 flex items-center justify-center px-4 py-12">
      <div
        class="w-full max-w-md space-y-8 bg-gray-950 rounded-2xl p-8 border border-gray-700 animate-[fadeUp_0.6s_ease-out]"
      >
        <div class="text-center">
          <div class="bg-yellow-500 rounded-full p-3 inline-block mx-auto mb-4">
            <svg
              class="h-8 w-8 text-blue-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2z"></path>
              <path d="M12 12m-5 0a5 5 0 1 0 10 0 5 5 0 1 0-10 0"></path>
            </svg>
          </div>
          <h2 class="text-3xl font-bold text-white">Bingo UETS</h2>
        </div>

        <div class="grid grid-cols-2 gap-2 bg-gray-900 p-1 rounded-xl" role="tablist">
          <button
            type="button"
            role="tab"
            [attr.aria-selected]="modo() === 'uets'"
            (click)="cambiarModo('uets')"
            [class]="modo() === 'uets' ? tabActiva : tabInactiva"
          >
            Estudiante / personal UETS
          </button>
          <button
            type="button"
            role="tab"
            [attr.aria-selected]="modo() === 'externo'"
            (click)="cambiarModo('externo')"
            [class]="modo() === 'externo' ? tabActiva : tabInactiva"
          >
            Público general
          </button>
        </div>

        @if (expirada && !error()) {
          <div
            class="bg-yellow-500/20 border border-yellow-500 text-yellow-200 p-3 rounded-lg text-sm"
          >
            Tu sesión expiró. Vuelve a iniciar sesión.
          </div>
        }
        @if (error()) {
          <div class="bg-red-500/20 border border-red-500 text-red-300 p-3 rounded-lg">
            {{ error() }}
          </div>
        }

        @if (registro(); as r) {
          <app-registro-estudiante
            [correo]="r.correo"
            [registroToken]="r.token"
            (registrado)="entrar($event)"
            (cancelado)="registro.set(null)"
          />
        }

        <div
          [class]="
            registro() || modo() === 'externo' ? 'hidden' : 'flex flex-col items-center gap-3'
          "
        >
          <p class="text-sm text-gray-400 text-center">
            Ingresa con tu cuenta institucional &#64;uets.edu.ec
          </p>
          <div #googleButton></div>
          @if (loading()) {
            <p class="text-sm text-gray-400">Validando cuenta...</p>
          }
        </div>

        <!-- Solo en desarrollo (ng serve): entra sin Google contra el backend de demo local. -->
        @if (modo() === 'externo') {
          <app-acceso-externo (entrar)="entrar($event)" />
        }

        @if (devMode && !registro()) {
          <div class="border border-dashed border-yellow-600 rounded-lg p-4 space-y-2">
            <p class="text-xs text-yellow-400 text-center">Login de prueba (solo desarrollo)</p>
            @for (u of usuariosDemo; track u.correo) {
              <button
                type="button"
                (click)="handleCredential(u.correo)"
                class="w-full bg-gray-800 hover:bg-gray-700 text-white rounded-lg px-4 py-2 text-sm"
              >
                Entrar como {{ u.rol }}
              </button>
            }
            <!-- Comprador externo de la demo: el backend de demo da la sesión sin pedir el código. -->
            <button
              type="button"
              (click)="entrarExternoDemo()"
              class="w-full bg-gray-800 hover:bg-gray-700 text-white rounded-lg px-4 py-2 text-sm"
            >
              Entrar como Externo (María Gómez)
            </button>
          </div>
        }

        @if (modo() === 'uets') {
          <p class="text-center text-sm text-gray-400">
            ¿Compraste tablas y no tienes cuenta institucional?
            <button
              type="button"
              (click)="cambiarModo('externo')"
              class="text-blue-400 hover:underline"
            >
              Entra como público general
            </button>
          </p>
        }
      </div>
    </div>
  `,
})
export class Login implements AfterViewInit, OnDestroy {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private readonly session = inject(SessionService);
  private readonly googleButton = viewChild.required<ElementRef<HTMLDivElement>>('googleButton');
  private destroyed = false;

  private readonly query = inject(ActivatedRoute).snapshot.queryParamMap;
  protected readonly expirada = !!this.query.get('expirada');
  /** 'uets' = Google (estudiantes y personal); 'externo' = cédula + correo + código. */
  protected readonly modo = signal<'uets' | 'externo'>(
    this.query.get('externo') ? 'externo' : 'uets',
  );
  protected readonly tabActiva =
    'py-2 rounded-lg text-sm font-semibold bg-yellow-500 text-gray-900';
  protected readonly tabInactiva = 'py-2 rounded-lg text-sm text-gray-300 hover:bg-gray-800';
  protected readonly error = signal('');
  protected readonly loading = signal(false);
  /** Datos para registrar a un estudiante que entra por primera vez. */
  protected readonly registro = signal<RegistroPendiente | null>(null);
  /** Login falso: solo existe en desarrollo y el backend real lo rechaza (no es un token de Google). */
  protected readonly devMode = isDevMode();
  protected readonly usuariosDemo = [
    { rol: 'Administrador', correo: 'admin.demo@uets.edu.ec' },
    { rol: 'Animador', correo: 'animador.demo@uets.edu.ec' },
    { rol: 'Secretaría', correo: 'secretaria.demo@uets.edu.ec' },
    { rol: 'Financiero', correo: 'financiero.demo@uets.edu.ec' },
    { rol: 'Parroquia', correo: 'parroquia.demo@uets.edu.ec' },
    { rol: 'Oratorio', correo: 'oratorio.demo@uets.edu.ec' },
    { rol: 'Estudiante', correo: 'estudiante.demo.est@uets.edu.ec' },
  ];

  async ngAfterViewInit(): Promise<void> {
    try {
      const google = await loadGoogleId();
      if (this.destroyed) return;
      google.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: ({ credential }) => void this.handleCredential(credential),
        ux_mode: 'popup',
      });
      google.renderButton(this.googleButton().nativeElement, {
        theme: 'filled_blue',
        size: 'large',
        shape: 'pill',
        text: 'signin_with',
        locale: 'es',
        width: 300,
      });
    } catch {
      this.error.set('No se pudo cargar el inicio de sesión de Google. Revise su conexión.');
    }
  }

  protected cambiarModo(modo: 'uets' | 'externo'): void {
    this.modo.set(modo);
    this.error.set('');
  }

  ngOnDestroy(): void {
    this.destroyed = true;
  }

  /** Solo desarrollo: sesión del comprador externo de la demo local (el sistema real pide el código). */
  protected async entrarExternoDemo(): Promise<void> {
    this.error.set('');
    try {
      this.entrar(
        await firstValueFrom(this.http.post<SesionResponse>(`${API_BASE_URL}/demo/externo`, {})),
      );
    } catch {
      this.error.set('El backend de demo local no está corriendo.');
    }
  }

  protected entrar(data: SesionResponse): void {
    this.session.save(data);
    void this.router.navigateByUrl(homeFor(data.usuario), { replaceUrl: true });
  }

  protected async handleCredential(credential: string): Promise<void> {
    this.error.set('');
    this.loading.set(true);
    try {
      this.entrar(
        await firstValueFrom(this.http.post<SesionResponse>('/api/auth/google', { credential })),
      );
    } catch (err) {
      const body = errorBody<{
        registro_requerido?: boolean;
        registro_token?: string;
        correo?: string;
      }>(err);
      if (body?.registro_requerido && body.registro_token) {
        this.registro.set({ token: body.registro_token, correo: body.correo || '' });
        return;
      }
      this.error.set(errorMessage(err, 'Error al conectar con el servidor'));
    } finally {
      this.loading.set(false);
    }
  }
}
