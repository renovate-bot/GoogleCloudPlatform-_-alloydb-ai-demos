import { Routes } from '@angular/router';
import { Dashboard } from './dashboard/dashboard';
import { JourneyPageComponent } from './journey-page-component/journey-page-component';

export const routes: Routes = [

  { path: 'home', component: JourneyPageComponent },
  { path: 'dashboard', component: Dashboard },
  { path: '', redirectTo: 'home', pathMatch: 'full' },
];
