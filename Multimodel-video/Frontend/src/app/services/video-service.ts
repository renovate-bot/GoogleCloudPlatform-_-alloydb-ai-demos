// videoService.service.ts
import { Injectable } from '@angular/core';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { Observable } from 'rxjs';

export type InputType = 'image' | 'text';

@Injectable({
  providedIn: 'root',
})
export class VideoService {
  private apiUrl = 'https://multimodal-video-search-service-888916268766.asia-south1.run.app/video_search';
  private categoriesUrl = 'https://multimodal-video-search-service-888916268766.asia-south1.run.app/categories_duration';

  constructor(private http: HttpClient) {}

  /**
   * Search videos.
   *
   * - If input_type === 'image', `query` is expected to be a data URL (base64) or an image URL.
   *   In that case the backend will treat `categories` as an empty string and `duration` will be 30 (per spec).
   * - If input_type === 'text', `query` is the user's text query; `categories` and `duration` are optional.
   *
   * @param query text query or base64/data-url for image
   * @param categories optional category key (empty string for image searches)
   * @param duration duration in seconds (for image searches backend expects 30)
   * @param input_type 'image' | 'text'
   */
  searchVideos(query: string, categories: string, duration: number, input_type: InputType): Observable<any> {
    const body: Record<string, any> = {
      query: query ?? '',
      categories: categories ?? '',
      duration: duration ?? 0,
      input_type: input_type ?? 'text',
    };

    const headers = new HttpHeaders({
      'Content-Type': 'application/json',
    });

    return this.http.post<any>(this.apiUrl, body, { headers });
  }

  /**
   * Fetch categories and their min/max durations from the API.
   * Expected response shape:
   * { "categories_duration": { "<category_key>": { "min_duration_sec": X, "max_duration_sec": Y }, ... } }
   */
  getCategoriesDuration(): Observable<any> {
    return this.http.get<any>(this.categoriesUrl);
  }
}
