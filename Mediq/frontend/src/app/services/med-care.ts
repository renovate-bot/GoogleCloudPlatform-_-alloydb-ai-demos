import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders, HttpErrorResponse } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError, map } from 'rxjs/operators';

export interface SummaryObj {
  summary?: string | null;
  source?: string | null;
}

export interface ImageObj {
  caption_text?: string | null;
  disease_image_base64?: string | null;
  image_page_num?: number | null;
  name_distance?: number | null;
}

export interface DetailItem {
  disease_name?: string | null;
  summary_pdf?: SummaryObj | null;
  summary_csv?: SummaryObj | null;
  details_chunks?: any[] | null;
  tests_details?: any[] | null;
  related_images?: ImageObj[] | null;
}

export interface ApiResponse {
  sql_command?: string | null;
  details?: DetailItem[] | null;
}

@Injectable({
  providedIn: 'root',
})
export class MedCare {
  private apinewUrl = 'https://medical-search-service-888916268766.asia-south1.run.app/medIqSearch';

  constructor(private http: HttpClient) {}

  getdetails(question: string): Observable<ApiResponse> {
    const trimmed = (question ?? '').trim();
    if (!trimmed) {
      return throwError(() => new Error('Empty query: please provide a non-empty question.'));
    }

    const body = { question: trimmed };
    const headers = new HttpHeaders({ 'Content-Type': 'application/json' });

    return this.http.post<ApiResponse>(this.apinewUrl, body, { headers }).pipe(
      map((resp) => ({
        sql_command: resp?.sql_command ?? null,
        details: Array.isArray(resp?.details) ? resp.details : resp?.details ? [resp.details] : null,
      })),
      catchError((err: HttpErrorResponse) => {
        console.error('MedCare HTTP error:', err);
        const serverMsg =
          err.error && typeof err.error === 'object' ? JSON.stringify(err.error) : err.error || err.message || 'Unknown server error';
        return throwError(() => new Error(`Request failed (${err.status}): ${serverMsg}`));
      })
    );
  }
}
