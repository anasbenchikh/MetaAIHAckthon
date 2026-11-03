import { Routes } from '@angular/router';
import { Dashboard } from './components/dashboard/dashboard';
import { Leads } from './components/leads/leads';

export const routes: Routes = [
  { path: '', component: Dashboard, pathMatch: 'full' },
  { path: 'leads', component: Leads },
  {
    path: 'appointments',
    loadComponent: () =>
      import('./components/appointments/appointments').then((m) => m.Appointments),
  },
  {
    path: 'quotes',
    loadComponent: () =>
      import('./components/quotes/quotes').then((m) => m.Quotes),
  },
  { path: '**', redirectTo: '' },
];
