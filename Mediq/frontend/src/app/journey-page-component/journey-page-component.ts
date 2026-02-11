import { Component } from '@angular/core';
import { RouterOutlet, Router } from '@angular/router';

@Component({
  selector: 'app-journey-page-component',
  imports: [],
  templateUrl: './journey-page-component.html',
  styleUrl: './journey-page-component.scss',
})
export class JourneyPageComponent {
    constructor(private router: Router) {}
  navigateDemo() {
  debugger;
  this.router.navigateByUrl('/search');
  }
}
