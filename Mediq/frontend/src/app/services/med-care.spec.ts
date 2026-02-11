import { TestBed } from '@angular/core/testing';

import { MedCare } from './med-care';

describe('MedCare', () => {
  let service: MedCare;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(MedCare);
  });

  it('should be created', () => {
    expect(service).toBeTruthy();
  });
});
