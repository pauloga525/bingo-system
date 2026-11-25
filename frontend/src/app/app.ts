import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

import { Cargando } from './shared/cargando';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, Cargando],
  template: '<router-outlet /><app-cargando />',
})
export class App {}
