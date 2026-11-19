// Carga de Google Identity Services (botón "Iniciar sesión con Google").

interface GoogleIdApi {
  initialize(config: {
    client_id: string;
    callback: (resp: { credential: string }) => void;
    ux_mode?: 'popup' | 'redirect';
  }): void;
  renderButton(parent: HTMLElement, options: Record<string, unknown>): void;
  disableAutoSelect?(): void;
}

declare global {
  interface Window {
    google?: { accounts?: { id?: GoogleIdApi } };
  }
}

const GSI_SRC = 'https://accounts.google.com/gsi/client';

/** Carga una sola vez el script de Google y devuelve su API. */
export const loadGoogleId = (): Promise<GoogleIdApi> =>
  new Promise((resolve, reject) => {
    const ready = () => {
      const api = window.google?.accounts?.id;
      if (api) resolve(api);
      else reject(new Error('Google no disponible'));
    };
    if (window.google?.accounts?.id) return ready();
    let script = document.querySelector<HTMLScriptElement>(`script[src="${GSI_SRC}"]`);
    if (!script) {
      script = document.createElement('script');
      script.src = GSI_SRC;
      script.async = true;
      script.defer = true;
      document.head.appendChild(script);
    }
    script.addEventListener('load', ready);
    script.addEventListener('error', () => reject(new Error('No se pudo cargar Google')));
  });
