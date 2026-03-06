import {
  Component,
  ChangeDetectorRef,
  ElementRef,
  ViewChild,
  OnInit,
  AfterViewInit,
  Inject,
  PLATFORM_ID,
} from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { HttpClientModule } from '@angular/common/http';
import { VideoService } from '../services/video-service';
import { RouterOutlet, Router } from '@angular/router';

interface VideoItem {
  id?: string | number;
  filename?: string;
  public_url?: string;
  url?: string;
  label?: string;
  labels?: string[];
  duration_seconds?: number;
  duration?: number;
  metadata?: any;
  [key: string]: any;
}

interface StoredSearch {
  query: string;                    // kept for backward-compat with text
  results: VideoItem[];
  timestamp: number;
  // Support both text and image searches
  input_type?: 'text' | 'image';
  key?: string;                     // text: trimmed query; image: hash of base64/url
  image_name?: string;              // optional (debug/UX)
}

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, FormsModule, HttpClientModule, RouterOutlet],
  templateUrl: './dashboard.html',
  styleUrls: ['./dashboard.scss'],
})
export class Dashboard implements OnInit, AfterViewInit {
  @ViewChild('qEl') qEl!: ElementRef<HTMLInputElement>;
  @ViewChild('durationRange') durationRange!: ElementRef<HTMLInputElement>;
  @ViewChild('imageInput') imageInput!: ElementRef<HTMLInputElement>;

  // Search / UI state
  query = '';
  selectedCategory = ''; // All categories by default

  // Duration handling
  duration = 0; // confirmed duration (used for summary + requests)
  pendingDuration: number | null = null; // live slider value while popup is open (unconfirmed)
  userSelectedDuration = false; // becomes true only after "Done"
  showDurationPopup = false;

  // === State control flags ===
  categoriesEnabled = false; // show dropdown but disabled initially
  sendEnabled = false; // send disabled initially
  durationEnabled = true; // managed together with categoriesEnabled

  loading = false;
  results: VideoItem[] = [];
  sqlQueryText = '';
  showSqlModal = false;

  showPlayer = false;
  currentVideoUrl = '';
  currentVideoTitle: string | undefined = undefined;

  categories: Array<{ value: string; label: string; min: number; max: number }> = [];
  // Snapshot of server-provided categories so we can restore them
  private originalCategories: Array<{ value: string; label: string; min: number; max: number }> = [];

  selectedCategoryMin = 0; // All categories default min
  selectedCategoryMax = 15; // All categories default max

  formError = '';
  extraSqlLines = `/* Retrieves video metadata and embeddings for similarity search. */`;
  includeExtraSql = true;
  showCopySuccess = false;
  private copyTimer: any = null;

  // Image upload state
  uploadedImageName = '';
  uploadedImageFile?: File;
  uploadedImagePreview: string | null = null;
  uploadedImageBase64: string | null = null;
  pastedImageUrl = '';
  showImageModal = false;
  allowRemove = true;

  // Local storage / stored search
  private lastStoredSearch: StoredSearch | null = null;
  private storageKey = 'multimodal_last_search';

  noVideosMessage = '';

  // Flags for cleared/new-question flow and stored-match logic
  private wasCleared = false;
  private pendingQueryKey = 'pending_query_after_clear';
  private storedMatchesInput = false;

  constructor(
    private videoService: VideoService,
    private cdr: ChangeDetectorRef,
    private router: Router,
    @Inject(PLATFORM_ID) private platformId: Object
  ) { }

  private get isBrowser(): boolean {
    return isPlatformBrowser(this.platformId);
  }

  // -------------------------
  // Safe storage helpers
  // -------------------------
  private safeLocalGet(key: string): string | null {
    if (!this.isBrowser) return null;
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  }
  private safeLocalSet(key: string, value: string): void {
    if (!this.isBrowser) return;
    try {
      localStorage.setItem(key, value);
    } catch { }
  }
  private safeLocalRemove(key: string): void {
    if (!this.isBrowser) return;
    try {
      localStorage.removeItem(key);
    } catch { }
  }
  private safeSessionGet(key: string): string | null {
    if (!this.isBrowser) return null;
    try {
      return sessionStorage.getItem(key);
    } catch {
      return null;
    }
  }
  private safeSessionSet(key: string, value: string): void {
    if (!this.isBrowser) return;
    try {
      sessionStorage.setItem(key, value);
    } catch { }
  }
  private safeSessionRemove(key: string): void {
    if (!this.isBrowser) return;
    try {
      sessionStorage.removeItem(key);
    } catch { }
  }

  // -------------------------
  // Lifecycle
  // -------------------------
  ngOnInit(): void {
    // Show loader while loading initial category durations
    this.setLoading(true);

    // Clear any old persisted search on page load (as in your original)
    window.addEventListener('load', () => {
      localStorage.removeItem('multimodal_last_search');
    });

    // Load categories durations from server
    this.videoService.getCategoriesDuration().subscribe({
      next: (res) => {
        const cd = res?.categories_duration ?? {};
        this.categories = Object.keys(cd).map((k) => {
          const entry = cd[k] ?? {};
          return {
            value: k,
            label: this.humanizeCategoryKey(k),
            min: Number(entry.min_duration_sec ?? 0),
            max: Number(entry.max_duration_sec ?? 15),
          };
        });
        // Snapshot the original categories so we can restore them
        this.originalCategories = this.categories.slice();
        setTimeout(() => this.updateRangeFill(), 0);
        this.cdr.markForCheck();
        this.setLoading(false);
      },
      error: (err) => {
        console.error('Failed to load categories_duration', err);
        this.setLoading(false);
      },
    });

    // Initial state: All categories, duration enabled (3..9s)
    this.selectedCategory = '';
    this.durationEnabled = true;
    this.selectedCategoryMin = 0;
    this.selectedCategoryMax = 15;

    // Keep internal default; UI summary will hide it until user confirms via Done
    if (typeof this.duration !== 'number' || this.duration < 0 || this.duration > 15) {
      this.duration = 0;
    }
    this.userSelectedDuration = false;

    // Lock filters and send on first load (visible but disabled)
    this.categoriesEnabled = false;
    this.durationEnabled = false;
    this.sendEnabled = false;

    // Restore pending query after reset if any
    try {
      const pending = this.safeSessionGet(this.pendingQueryKey);
      if (pending !== null) {
        this.query = pending;
        this.safeSessionRemove(this.pendingQueryKey);
        this.wasCleared = false;
        setTimeout(() => {
          try {
            this.qEl?.nativeElement?.focus();
          } catch { }
        }, 50);
      }
    } catch (err) {
      console.warn('Failed to restore pending query', err);
    }
  }

  ngAfterViewInit(): void {
    setTimeout(() => this.updateRangeFill(), 0);
  }

  // -------------------------
  // Utility helpers
  // -------------------------
  private humanizeCategoryKey(key: string): string {
    return key
      .split('_')
      .map((s) => (s.length ? s[0].toUpperCase() + s.slice(1) : s))
      .join(' ');
  }

  // Simple, fast hash (no crypto) to avoid storing full base64 in localStorage
  private hashString(s: string): string {
    let h = 5381;
    for (let i = 0; i < s.length; i++) h = ((h << 5) + h) ^ s.charCodeAt(i);
    return (h >>> 0).toString(36);
  }

  // Build a stable identity for the current input (text or image)
  private currentSearchKey(): { type: 'text' | 'image'; key: string } | null {
    const trimmed = (this.query ?? '').trim();
    if (this.uploadedImagePreview) {
      const raw = this.uploadedImageBase64 || this.uploadedImagePreview; // base64 or URL
      const key = this.hashString(raw);
      return { type: 'image', key };
    } else if (trimmed) {
      return { type: 'text', key: trimmed };
    }
    return null;
  }

  // Compare current UI input vs. what's stored
  private storedMatchesCurrentInput(): boolean {
    if (!this.lastStoredSearch) return false;
    const cur = this.currentSearchKey();
    if (!cur) return false;
    return (
      this.lastStoredSearch.input_type === cur.type &&
      typeof this.lastStoredSearch.key === 'string' &&
      this.lastStoredSearch.key === cur.key
    );
  }

  onQueryInput(): void {
    const currentRaw = this.query ?? '';
    const current = currentRaw.trim();

    // While typing: filters disabled, send enabled if non-empty
    if (current.length > 0) {
      this.categoriesEnabled = false;
      this.durationEnabled = false;
      this.sendEnabled = true;
    } else {
      this.categoriesEnabled = false;
      this.durationEnabled = false;
      this.sendEnabled = false;
    }

    if (current === '') {
      this.wasCleared = true;
      this.results = [];
      this.sqlQueryText = '';
      this.noVideosMessage = '';
      this.showSqlModal = false;
      this.showPlayer = false;
      this.currentVideoUrl = '';
      this.currentVideoTitle = undefined;
      this.cdr.markForCheck();
      return;
    }

    // If user is typing a new question (not equal to last searched), restore original categories
    if (!this.lastStoredSearch || this.lastStoredSearch.query !== current) {
      this.restoreAllCategories();
    }

    if (this.wasCleared) {
      this.wasCleared = false;
      try {
        // Save typed text so it can be restored after reset
        this.safeSessionSet(this.pendingQueryKey, currentRaw);
        // Reset app state without full reload
        this.resetAppState();
      } catch (err) {
        console.warn('Failed to prepare reset', err);
      }
      return;
    }

    // Normal typing: clear displayed results
    this.results = [];
    this.sqlQueryText = '';
    this.noVideosMessage = '';
    this.showSqlModal = false;
    this.showPlayer = false;
    this.currentVideoUrl = '';
    this.currentVideoTitle = undefined;
    this.cdr.markForCheck();
  }

  private resetAppState(): void {
    // 1) Clear persisted stored search
    try {
      this.safeLocalRemove(this.storageKey);
      this.lastStoredSearch = null;
    } catch (err) {
      console.warn('Failed to remove stored search from localStorage', err);
    }

    // 2) Reset UI state
    this.results = [];
    this.sqlQueryText = '';
    this.noVideosMessage = '';
    this.showSqlModal = false;
    this.showPlayer = false;
    this.currentVideoUrl = '';
    this.currentVideoTitle = undefined;

    // Reset controls to defaults (All categories)
    this.selectedCategory = '';
    this.duration = 0;
    this.pendingDuration = null;
    this.userSelectedDuration = false;
    this.durationEnabled = true;
    this.showDurationPopup = false;
    this.selectedCategoryMin = 0;
    this.selectedCategoryMax = 15;

    // Reset enable/disable flags
    this.categoriesEnabled = false;
    this.durationEnabled = false;
    this.sendEnabled = false;

    // Clear image upload state
    this.uploadedImageName = '';
    this.uploadedImageFile = undefined;
    this.uploadedImagePreview = null;
    this.uploadedImageBase64 = null;
    this.pastedImageUrl = '';
    this.allowRemove = true;
    try {
      if (this.imageInput?.nativeElement) this.imageInput.nativeElement.value = '';
    } catch { }

    // 3) Re-run initialization logic: fetch categories and snapshot original
    try {
      this.videoService.getCategoriesDuration().subscribe({
        next: (res) => {
          const cd = res?.categories_duration ?? {};
          this.categories = Object.keys(cd).map((k) => {
            const entry = cd[k] ?? {};
            return {
              value: k,
              label: this.humanizeCategoryKey(k),
              min: Number(entry.min_duration_sec ?? 0),
              max: Number(entry.max_duration_sec ?? 15),
            };
          });
          this.originalCategories = this.categories.slice();
          setTimeout(() => this.updateRangeFill(), 0);
          this.cdr.markForCheck();
        },
        error: (err) => {
          console.warn('Failed to reload categories', err);
        },
      });
    } catch (err) {
      console.warn('resetAppState: failed to refresh categories', err);
    }

    // 4) Focus input after a short delay
    setTimeout(() => {
      try {
        this.qEl?.nativeElement?.focus();
      } catch { }
      this.cdr.markForCheck();
    }, 50);
  }

  toggleDurationPopup() {
    if (!this.durationEnabled || this.loading) return;
    if (!this.showDurationPopup) {
      // Opening → initialize pending value from current confirmed duration, clamped
      let start = this.duration;
      if (start < this.selectedCategoryMin) start = this.selectedCategoryMin;
      if (start > this.selectedCategoryMax) start = this.selectedCategoryMax;
      this.pendingDuration = start;
      setTimeout(() => this.updateRangeFill(), 0);
    } else {
      // Closing without Done → discard pending
      this.pendingDuration = null;
    }
    this.showDurationPopup = !this.showDurationPopup;
    this.cdr.markForCheck();
  }

  setDurationFromSlider(value: Event | number | string) {
    // Update PENDING value only (do not confirm until Done)
    let v: number;
    if (value instanceof Event) {
      const input = value.target as HTMLInputElement | null;
      v = input ? Number(input.value) : (this.pendingDuration ?? this.duration);
    } else {
      v = typeof value === 'string' ? parseFloat(value) : Number(value);
    }
    let newVal = Math.round(isNaN(v) ? (this.pendingDuration ?? this.duration) : v);
    if (this.durationEnabled) {
      if (newVal < this.selectedCategoryMin) newVal = this.selectedCategoryMin;
      if (newVal > this.selectedCategoryMax) newVal = this.selectedCategoryMax;
    }
    this.pendingDuration = newVal;
    // Do NOT set userSelectedDuration here; wait for Done
    this.updateRangeFill();
    this.cdr.markForCheck();
  }

  private updateRangeFill() {
    try {
      const el = this.durationRange?.nativeElement;
      if (!el) return;
      const min = Number(el.min || this.selectedCategoryMin || 0);
      const max = Number(el.max || this.selectedCategoryMax || 100);
      const val = Number((this.pendingDuration ?? this.duration) || el.value || 0);
      const pct = max > min ? ((val - min) / (max - min)) * 100 : 0;
      el.style.setProperty('--range-percent', `${pct}%`);
      if (String(el.value) !== String(val)) el.value = String(val);
    } catch (err) {
      console.warn('updateRangeFill failed', err);
    }
  }

  private setLoading(on: boolean) {
    this.loading = on;
    if (on) document.body.classList.add('loading-active');
    else document.body.classList.remove('loading-active');
    this.cdr.markForCheck();
  }

  displayQueryTitle(): string {
    if (this.uploadedImagePreview) return 'Image search';
    return this.query || this.selectedCategory || '';
  }

  submitSearch(e?: Event) {
    if (e) e.preventDefault();

    this.showDurationPopup = false;
    // Confirm pending change if popup was open and user didn't click Done but now submits search
    if (this.pendingDuration !== null) {
      this.duration = this.pendingDuration;
      this.userSelectedDuration = true;
      this.pendingDuration = null;
    }

    // Once user submits, disable send immediately
    this.sendEnabled = false;
    this.cdr.markForCheck();

    const isImage = !!this.uploadedImagePreview;
    const trimmedText = (this.query || '').trim();

    // Guard against empty or script-like input
    const scriptLike = /<script.*?>.*?<\/script>/i.test(trimmedText);
    if (!isImage && (!trimmedText || scriptLike)) {
      this.formError = '';
      this.results = [];
      this.sqlQueryText = '';
      this.noVideosMessage = 'Enter a relevant search term, or choose from the suggested questions above';
      try {
        this.qEl?.nativeElement?.focus();
      } catch { }
      this.cdr.markForCheck();
      return;
    }

    this.formError = '';
    this.noVideosMessage = '';

    // If text search and query changed from last stored => reset filters/results + restore categories
    if (!isImage) {
      if (!this.lastStoredSearch || this.lastStoredSearch.query !== trimmedText) {
        this.selectedCategory = '';
        // keep internal default; summary shows "—" unless user confirms
        this.duration = 0;
        this.pendingDuration = null;
        this.userSelectedDuration = false;
        this.durationEnabled = true;
        this.results = [];
        this.sqlQueryText = '';
        this.lastStoredSearch = null;
        try {
          this.safeLocalRemove(this.storageKey);
        } catch { }
        // Ensure dropdown shows full list before search runs
        this.restoreAllCategories();
      }
    }

    let payloadQuery: string;
    let payloadCategory: string;
    let payloadDuration: number;
    let input_type: 'image' | 'text';

    if (isImage) {
      if (this.uploadedImagePreview && /^https?:\/\//i.test(this.uploadedImagePreview)) {
        payloadQuery = this.uploadedImagePreview;
        this.uploadedImageBase64 = null;
      } else if (this.uploadedImageBase64) {
        payloadQuery = this.uploadedImageBase64;
      } else {
        const preview = this.uploadedImagePreview || '';
        payloadQuery = preview.includes(',') ? preview.split(',')[1] : preview;
      }
      payloadCategory = '';
      payloadDuration = 30; // image-search duration constant
      input_type = 'image';
      this.allowRemove = false; // will be re-enabled after the request completes
    } else {
      payloadQuery = trimmedText;
      payloadCategory = this.selectedCategory || '';
      // If user never clicked Done, use 15s; else use confirmed duration
      payloadDuration = this.userSelectedDuration ? this.duration : 15;
      input_type = 'text';
    }

    this.setLoading(true);
    this.results = [];
    this.showSqlModal = false;

    this.videoService.searchVideos(payloadQuery, payloadCategory, payloadDuration, input_type).subscribe({
      next: (res) => {
        const vd = res?.video_details;
        const baseSql = (vd?.sql_query ?? '').trim();
        const extra = (this.includeExtraSql ? (this.extraSqlLines || '') : '').trim();
        if (baseSql && extra) this.sqlQueryText = `${extra}\n\n${baseSql}`;
        else if (baseSql) this.sqlQueryText = baseSql;
        else this.sqlQueryText = extra;

        this.results = (vd?.multimodal_video_search ?? []) as VideoItem[];

        // Persist for both text and image with a stable key
        const cur = this.currentSearchKey();
        if (cur) {
          const store: StoredSearch = {
            query: cur.type === 'text' ? cur.key : '',
            results: this.results.slice(),
            timestamp: Date.now(),
            input_type,           // 'text' | 'image'
            key: cur.key,         // stable identity
            image_name: this.uploadedImageName ?? undefined,
          };
          try {
            this.safeLocalSet(this.storageKey, JSON.stringify(store));
            this.lastStoredSearch = store;
          } catch (err) {
            console.warn('Failed to save last search to localStorage', err);
          }
        }

        // After search, rebuild categories from labels in results (with fallback)
        this.refreshCategoriesFromResults(this.results);

        // Friendly guidance
        if (!this.results.length) {
          this.noVideosMessage = 'Enter a relevant search term, or choose from the suggested questions above';
        } else {
          this.noVideosMessage = '';
        }

        // After results arrive → enable category & duration; keep send disabled
        this.categoriesEnabled = true;
        this.durationEnabled = true;
        this.sendEnabled = false;

        // Re-allow removing image after search completes
        this.allowRemove = true;

        this.setLoading(false);
        this.cdr.markForCheck();
      },
      error: (err) => {
        console.error('Search error', err);
        this.noVideosMessage = 'Enter a relevant search term, or choose from the suggested questions above';
        // On error, keep filters disabled; allow retry if text exists
        this.categoriesEnabled = false;
        this.durationEnabled = false;
        this.sendEnabled = (this.query?.trim()?.length ?? 0) > 0;

        // Re-allow image removal on error as well
        this.allowRemove = true;

        this.setLoading(false);
      },
    });
  }

  openSqlModal() {
    if (this.showDurationPopup) {
      // Close popup WITHOUT applying (user didn't click Done)
      this.showDurationPopup = false;
      this.pendingDuration = null;
    }
    this.showSqlModal = true;
    document.body.classList.add('modal-open');
    this.cdr.markForCheck();
  }

  closeSqlModal() {
    this.showSqlModal = false;
    document.body.classList.remove('modal-open');
    this.cdr.markForCheck();
  }

  openPlayer(video: VideoItem | undefined) {
    if (!video) return;
    if (this.showDurationPopup) {
      // Close popup WITHOUT applying (user didn't click Done)
      this.showDurationPopup = false;
      this.pendingDuration = null;
    }
    this.currentVideoUrl = video.public_url ?? video.url ?? '';
    this.currentVideoTitle = video.filename ?? this.currentVideoUrl ?? undefined;
    this.showPlayer = true;
    document.body.classList.add('modal-open');
    this.cdr.markForCheck();
  }

  closePlayer() {
    this.showPlayer = false;
    this.currentVideoUrl = '';
    this.currentVideoTitle = undefined;
    document.body.classList.remove('modal-open');
    this.cdr.markForCheck();
  }

  setSampleQuery(q: string, resetControls = true) {
    this.query = q;
    this.results = [];
    this.sqlQueryText = '';
    this.formError = '';
    this.noVideosMessage = '';
    if (resetControls) {
      this.selectedCategory = '';
      this.duration = 0;
      this.pendingDuration = null;
      this.userSelectedDuration = false;
      this.durationEnabled = true;
      this.showDurationPopup = false;
      this.selectedCategoryMin = 0;
      this.selectedCategoryMax = 15;

      this.uploadedImageName = '';
      this.uploadedImageFile = undefined;
      this.uploadedImagePreview = null;
      this.uploadedImageBase64 = null;
      this.pastedImageUrl = '';
      this.allowRemove = true;
      try {
        if (this.imageInput?.nativeElement) this.imageInput.nativeElement.value = '';
      } catch { }

      // Restore full categories list for the new question
      this.restoreAllCategories();
      setTimeout(() => this.updateRangeFill(), 0);
    }

    // Typing-equivalent state for a prefilled sample
    this.categoriesEnabled = false;
    this.durationEnabled = false;
    this.sendEnabled = (q?.trim()?.length ?? 0) > 0;

    this.showPlayer = false;
    this.currentVideoUrl = '';
    this.currentVideoTitle = undefined;
    this.showSqlModal = false;
    document.body.classList.remove('modal-open');

    try {
      this.qEl?.nativeElement?.focus();
    } catch { }
    this.cdr.markForCheck();
  }

  goToHome() {
    this.router.navigateByUrl('/home');
  }

  downloadSql(): void {
    const text = (this.sqlQueryText ?? '').trim();
    if (!text) return;
    try {
      const blob = new Blob([text], { type: 'text/sql;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'query.sql';
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Download failed', err);
    }
  }

  async copySql(): Promise<void> {
    const text = (this.sqlQueryText ?? '').trim();
    if (!text) return;
    try {
      if (this.isBrowser && navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      this.showCopySuccess = true;
      this.cdr.markForCheck();
      if (this.copyTimer) clearTimeout(this.copyTimer);
      this.copyTimer = setTimeout(() => {
        this.showCopySuccess = false;
        this.cdr.markForCheck();
      }, 2200);
    } catch (err) {
      console.error('Copy failed', err);
    }
  }

  openImageModal(): void {
    this.showImageModal = true;
    this.allowRemove = true;
    document.body.classList.add('modal-open');
    this.cdr.markForCheck();
  }

  closeImageModal(): void {
    this.showImageModal = false;
    document.body.classList.remove('modal-open');
    this.cdr.markForCheck();
  }

  triggerImageInput(): void {
    try {
      this.selectedCategory = '';
      this.duration = 0;
      this.pendingDuration = null;
      this.userSelectedDuration = false;
      this.durationEnabled = true;
      this.showDurationPopup = false;
      this.selectedCategoryMin = 0;
      this.selectedCategoryMax = 15;

      this.uploadedImageName = '';
      this.uploadedImageFile = undefined;
      this.uploadedImagePreview = null;
      this.uploadedImageBase64 = null;
      this.pastedImageUrl = '';
      this.allowRemove = true;
      this.imageInput?.nativeElement?.click();
    } catch (err) {
      this.selectedCategory = '';
      this.duration = 0;
      this.pendingDuration = null;
      this.userSelectedDuration = false;
      this.durationEnabled = true;
      this.showDurationPopup = false;
      this.selectedCategoryMin = 0;
      this.selectedCategoryMax = 15;

      this.uploadedImageName = '';
      this.uploadedImageFile = undefined;
      this.uploadedImagePreview = null;
      this.uploadedImageBase64 = null;
      this.pastedImageUrl = '';
      this.allowRemove = true;
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = 'image/*';
      (input as any).onchange = (e: Event) => this.onImageSelected(e as any);
      input.click();
    }
  }

  onImageSelected(e: Event | any): void {
    try {
      const inputEl = (e?.target || e) as HTMLInputElement;
      const files = inputEl?.files;
      if (!files || files.length === 0) return;
      const file = files[0];
      if (!file.type.startsWith('image/')) return;

      this.uploadedImageFile = file;
      this.uploadedImageName = file.name || 'selected-image';
      this.selectedCategory = "";
      if (typeof this.duration !== 'number' || this.duration < 0 || this.duration > 15) {
        this.duration = 0;
      }
      this.userSelectedDuration = false;
      this.categoriesEnabled = false;
      this.durationEnabled = false;
      this.sendEnabled = true;

      const reader = new FileReader();
      reader.onload = (ev: any) => {
        const dataUrl: string = ev.target.result || '';
        this.uploadedImagePreview = dataUrl;
        const commaIndex = dataUrl.indexOf(',');
        this.uploadedImageBase64 = commaIndex >= 0 ? dataUrl.substring(commaIndex + 1) : dataUrl;
        this.query = '';
        this.noVideosMessage = '';
        this.cdr.markForCheck();
      };
      reader.readAsDataURL(file);
    } catch (err) {
      console.error('Image selection failed', err);
    }
  }

  onDragOver(evt: DragEvent) {
    evt.preventDefault();
    (evt.currentTarget as HTMLElement)?.classList?.add('dragover');
  }

  onDragLeave(evt: DragEvent) {
    evt.preventDefault();
    (evt.currentTarget as HTMLElement)?.classList?.remove('dragover');
  }

  onDrop(evt: DragEvent) {
    evt.preventDefault();
    (evt.currentTarget as HTMLElement)?.classList?.remove('dragover');
    const files = evt.dataTransfer?.files;
    if (!files || files.length === 0) return;
    const file = files[0];
    if (!file.type.startsWith('image/')) return;

    this.uploadedImageFile = file;
    this.uploadedImageName = file.name || 'dropped-image';

    const reader = new FileReader();
    reader.onload = (ev: any) => {
      const dataUrl: string = ev.target.result || '';
      this.uploadedImagePreview = dataUrl;
      const commaIndex = dataUrl.indexOf(',');
      this.uploadedImageBase64 = commaIndex >= 0 ? dataUrl.substring(commaIndex + 1) : dataUrl;
      this.query = '';
      this.noVideosMessage = '';
      this.cdr.markForCheck();
    };
    reader.readAsDataURL(file);
  }

  usePastedUrl(): void {
    if (!this.pastedImageUrl) return;
    const url = this.pastedImageUrl.trim();
    if (!/^https?:\/\//i.test(url)) return;
    this.uploadedImagePreview = url;
    this.uploadedImageName = url.split('/').pop() || url;
    this.uploadedImageFile = undefined;
    this.uploadedImageBase64 = null;
    this.query = '';
    this.noVideosMessage = '';
    this.cdr.markForCheck();
  }

  removeImage(): void {
    if (!this.allowRemove) return;
    this.uploadedImageName = '';
    this.uploadedImageFile = undefined;
    this.uploadedImagePreview = null;
    this.uploadedImageBase64 = null;
    this.pastedImageUrl = '';
    try {
      if (this.imageInput?.nativeElement) this.imageInput.nativeElement.value = '';
    } catch { }
    try {
      this.qEl?.nativeElement?.focus();
    } catch { }
    this.noVideosMessage = '';
    this.cdr.markForCheck();
  }

  onCategoryChange(value: string) {
    this.selectedCategory = value;
    this.durationEnabled = true;
    // if (typeof this.duration !== 'number' || this.duration < 0 || this.duration > 15) {
    //   this.duration = 0;
    // }
    this.duration = 15;
    this.userSelectedDuration = false;

    if (value === '') {
      this.selectedCategoryMin = 0;
      this.selectedCategoryMax = 15;
      if (typeof this.duration !== 'number' || this.duration < 0 || this.duration > 15) {
        this.duration = 0;
      }
      // keep userSelectedDuration unchanged
    } else {
      const cat = this.categories.find((c) => c.value === value);
      if (cat) {
        this.selectedCategoryMin = Number(cat.min ?? 0);
        this.selectedCategoryMax = Number(cat.max ?? 15);
        // keep the current confirmed duration but clamp to range
        if (this.duration < this.selectedCategoryMin) this.duration = this.selectedCategoryMin;
        if (this.duration > this.selectedCategoryMax) this.duration = this.selectedCategoryMax;
      } else {
        this.selectedCategoryMin = 0;
        this.selectedCategoryMax = 15;
      }
    }

    // Clear transient UI messages but keep sqlQueryText visible
    this.noVideosMessage = '';
    this.formError = '';

    // Unified stored-match check (works for both text and image)
    this.storedMatchesInput = this.storedMatchesCurrentInput();

    if (this.storedMatchesInput && this.lastStoredSearch) {
      if (!this.selectedCategory) {
        if (Array.isArray(this.lastStoredSearch.results) && this.lastStoredSearch.results.length) {
          this.results = this.lastStoredSearch.results.slice();
          this.noVideosMessage = '';
        } else {
          this.results = [];
          this.noVideosMessage =
            'No videos were found for the question you searched under this category';
        }
        this.showDurationPopup = false;
        this.cdr.markForCheck();
        return;
      }

      const source = this.lastStoredSearch.results.slice();
      const filteredByLabel = source.filter((item) =>
        this.itemMatchesLabel(item, this.selectedCategory)
      );

      if (filteredByLabel.length) {
        this.results = filteredByLabel;
        this.noVideosMessage = '';
      } else {
        this.results = [];
        this.noVideosMessage =
          'No videos were found for the question you searched under this category';
      }
      this.showPlayer = false;
      this.currentVideoUrl = '';
      this.currentVideoTitle = undefined;
      this.cdr.markForCheck();
      return;
    }

    // If stored does not match input (or no stored search), clear results and wait for apply/submit
    this.results = [];
    this.noVideosMessage = '';
    this.showPlayer = false;
    this.currentVideoUrl = '';
    this.currentVideoTitle = undefined;
    this.cdr.markForCheck();
  }

  applyCategoryDurationFilter(): void {
    this.showDurationPopup = false;

    // Confirm pending change (if any)
    if (this.pendingDuration !== null) {
      this.duration = this.pendingDuration;
      this.userSelectedDuration = true;
      this.pendingDuration = null;
    }

    this.noVideosMessage = '';

    // Use generic stored-match logic (text or image)
    const storedMatches = this.storedMatchesCurrentInput();

    if (storedMatches && this.lastStoredSearch && Array.isArray(this.lastStoredSearch.results)) {
      const sourceResults = this.lastStoredSearch.results.slice();

      // 1) Filter by selected category (if any)
      let filtered = this.selectedCategory
        ? sourceResults.filter((item) => this.itemMatchesLabel(item, this.selectedCategory))
        : sourceResults;

      // 2) Apply duration filter (<= selected duration, respecting category min)
      const applyDuration = !!this.durationEnabled && Number.isFinite(Number(this.duration));
      if (applyDuration) {
        filtered = filtered.filter((item) =>
          this.itemMatchesDurationForLabel(item, this.duration)
        );
      }

      if (filtered.length > 0) {
        this.results = filtered;
        this.noVideosMessage = '';
        this.cdr.markForCheck();
        return;
      }

      // No matches → show message
      this.results = [];
      this.noVideosMessage =
        'No videos were found for the selected duration under this category';
      this.cdr.markForCheck();
      return;
    }

    // If no stored search exists (or input changed), fallback to fresh API search
    const trimmedText = (this.query || '').trim();
    if (!trimmedText && !this.uploadedImagePreview) {
      this.formError = 'Please enter a search query or upload an image before applying filters.';
      this.cdr.markForCheck();
      return;
    }

    // Perform a fresh search using current input + selected category/duration
    this.submitSearch();
  }

  private itemMatchesLabel(item: any, categoryValue: string): boolean {
    if (!item || !categoryValue) return false;
    const humanized = this.humanizeCategoryKey(categoryValue).toLowerCase();
    const catLower = String(categoryValue).toLowerCase();

    const label = item?.label;
    const labels = item?.labels;

    if (typeof label === 'string') {
      const l = label.trim().toLowerCase();
      if (l === catLower || l === humanized) return true;
    }
    if (Array.isArray(labels)) {
      for (const x of labels) {
        if (!x) continue;
        const s = String(x).trim().toLowerCase();
        if (s === catLower || s === humanized) return true;
      }
    }
    return false;
  }

  private itemMatchesDurationForLabel(item: any, selectedDurationSec: number): boolean {
    if (!item) return false;
    const possibleFields = [
      'duration_seconds',
      'duration',
      'video_duration',
      'length_sec',
      'length_seconds',
      'durationSec',
    ];
    let itemDurationSec: number | null = null;

    for (const f of possibleFields) {
      if (item[f] !== undefined && item[f] !== null) {
        const n = Number(item[f]);
        if (!isNaN(n)) {
          itemDurationSec = n;
          break;
        }
      }
    }
    if (itemDurationSec === null && item.metadata && typeof item.metadata === 'object') {
      for (const f of possibleFields) {
        if (item.metadata[f] !== undefined && item.metadata[f] !== null) {
          const n = Number(item.metadata[f]);
          if (!isNaN(n)) {
            itemDurationSec = n;
            break;
          }
        }
      }
    }
    if (itemDurationSec === null) return false;

    const cat = this.categories.find((c) => c.value === this.selectedCategory);
    const catMin = this.selectedCategory === '' ? 0 : cat ? Number(cat.min || 0) : 0;
    const selDur = Number(selectedDurationSec);

    return itemDurationSec >= catMin && itemDurationSec <= selDur;
    // Note: duration is applied as "≤ selected duration" with category min respected
  }

  private loadLastSearchFromStorage(): void {
    try {
      const raw = this.safeLocalGet(this.storageKey);
      if (!raw) return;
      const parsed = JSON.parse(raw) as StoredSearch;
      if (parsed && parsed.query && Array.isArray(parsed.results)) {
        this.lastStoredSearch = parsed;
      }
    } catch (err) {
      console.warn('Failed to parse stored last search', err);
    }
  }

  openUserGuide(): void {
    try {
      const url = '/assets/images/Multimodal Video Incident Identification User Guide 2.pdf';
      const a = document.createElement('a');
      a.href = url; a.target = '_blank';
      a.rel = 'noopener noreferrer';
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (e) {
      console.error('Failed to open user guide in new tab', e);
    }
  }

  // Build categories from labels in results (after a search) with resilient fallback
  private refreshCategoriesFromResults(items: VideoItem[]): void {
    const found = new Map<string, string>(); // key: normalized value, value: display label
    const pushLabel = (raw: string) => {
      if (!raw) return;
      const label = String(raw).trim();
      if (!label) return;
      const value = label.toLowerCase().replace(/\s+/g, '_');
      if (!found.has(value)) {
        found.set(value, this.toTitleCase(label));
      }
    };

    for (const item of items || []) {
      if (typeof item?.label === 'string') pushLabel(item.label);
      if (Array.isArray(item?.labels)) {
        for (const l of item.labels) pushLabel(String(l || ''));
      }
    }

    if (found.size > 0) {
      const prevSelected = this.selectedCategory;
      this.categories = Array.from(found.entries()).map(([value, label]) => ({
        value,
        label,
        min: 0,
        max: 15,
      }));
      const stillExists = this.categories.some((c) => c.value === prevSelected);
      this.selectedCategory = stillExists ? prevSelected : '';
    } else {
      // Fallback: use the full original list so the dropdown is never empty
      if (Array.isArray(this.originalCategories) && this.originalCategories.length) {
        this.categories = this.originalCategories.slice();
        this.selectedCategory = '';
      }
    }

    // Keep duration rail sane based on current selection
    if (this.selectedCategory) {
      const cat = this.categories.find(c => c.value === this.selectedCategory);
      this.selectedCategoryMin = cat?.min ?? 0;
      this.selectedCategoryMax = cat?.max ?? 15;
    } else {
      this.selectedCategoryMin = 0;
      this.selectedCategoryMax = 15;
    }

    setTimeout(() => this.updateRangeFill(), 0);
    this.cdr.markForCheck();
  }

  private toTitleCase(s: string): string {
    return s
      .toLowerCase()
      .replace(/\b\w/g, (ch) => ch.toUpperCase())
      .replace(/\_/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  // Restore the original full category list and reset to "All Categories"
  private restoreAllCategories(): void {
    if (Array.isArray(this.originalCategories) && this.originalCategories.length) {
      this.categories = this.originalCategories.slice();
    }
    this.selectedCategory = '';
    this.selectedCategoryMin = 0;
    this.selectedCategoryMax = 15;
    setTimeout(() => this.updateRangeFill(), 0);
    this.cdr.markForCheck();
  }
}
