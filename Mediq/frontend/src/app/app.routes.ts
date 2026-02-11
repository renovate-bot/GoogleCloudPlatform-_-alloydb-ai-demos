import { Routes } from '@angular/router';
import { Search } from './search/search';
import { JourneyPageComponent } from './journey-page-component/journey-page-component';

export const routes: Routes = [

  { path:'search',component: Search},
  { path: 'home', component: JourneyPageComponent },
  { path: '', redirectTo: 'home', pathMatch: 'full' },
];
