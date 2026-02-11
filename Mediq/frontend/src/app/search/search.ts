import { CommonModule } from '@angular/common';
import { Component, ViewChild, ElementRef, OnDestroy, ChangeDetectorRef } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import { ApiResponse, DetailItem, MedCare } from '../services/med-care';
import { RouterOutlet, Router } from '@angular/router';
interface SummaryCsvRaw {
  summary?: string | string[] | null;
  source?: string | null;
}

type DetailItemExtended = Omit<DetailItem, 'summary_csv'> & {
  summary_csv?: SummaryCsvRaw | null;
  summary_csv_raw?: string | null;
  tests_details?: any;
};

@Component({
  selector: 'app-search',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterOutlet],
  templateUrl: './search.html',
  styleUrls: ['./search.scss'],
})
export class Search implements OnDestroy {
  query = '';
  error: string | null = null;
  resultMessage: string | null = null;

  loading = false;
  results: DetailItemExtended | null = null;
  sqlCommand: string | null = null;
  showSqlModal = false;

  showCopySuccess = false;
  private copyTimer: any = null;

  private apiSub: Subscription | null = null;

  @ViewChild('qInput', { static: false }) qInput?: ElementRef<HTMLInputElement>;

  constructor(private medCare: MedCare, private cdr: ChangeDetectorRef, private router: Router) { }

  private isNilToken(value: unknown): boolean {
    return typeof value === 'string' && value.trim().toUpperCase() === 'NIL';
  }

  useChip(text: string): void {
    this.clearMessages();
    this.query = text;
    setTimeout(() => {
      this.qInput?.nativeElement.focus();
      this.cdr.markForCheck();
    }, 0);
  }

  onSubmit(): void {
    this.clearMessages();

    const trimmed = (this.query ?? '').trim();
    if (!trimmed) {
      this.error = 'Enter the query or try selecting the below.';
      this.cdr.markForCheck();
      return;
    }

    this.loading = true;
    this.results = null;
    this.sqlCommand = null;
    this.resultMessage = null;
    this.cdr.markForCheck();

    this.apiSub = this.medCare.getdetails(trimmed).subscribe({
      next: (resp: ApiResponse) => {
        this.sqlCommand = resp?.sql_command ?? null;
        const first = Array.isArray(resp?.details) && resp.details.length ? resp.details[0] : null;

        if (first) {
          if (first.summary_csv && typeof first.summary_csv === 'object') {
            const csvSummary = (first.summary_csv as any).summary;
            if (this.isNilToken(csvSummary)) {
              (first.summary_csv as any).summary = null;
            }
          }

          if (typeof first.summary_csv === 'string' && this.isNilToken(first.summary_csv)) {
            first.summary_csv = null;
          }

          if (first.summary_pdf && typeof first.summary_pdf === 'object') {
            const pdfSummary = (first.summary_pdf as any).summary;
            if (this.isNilToken(pdfSummary)) {
              (first.summary_pdf as any).summary = null;
            }
          }
        }

        const rawCsv = first?.summary_csv ?? null;
        const rawCsvString =
          typeof rawCsv === 'string' ? rawCsv : Array.isArray(rawCsv) ? rawCsv.map(String).join('\n') : null;

        const rawTests = first?.tests_details ?? null;
        const normalizedTests = Array.isArray(rawTests)
          ? rawTests.map((t: any) => (typeof t === 'string' ? t.replace(/^["']+|["']+$/g, '').trim() : t))
          : rawTests;

        const hasSummaryCsv =
          (rawCsvString && rawCsvString.trim().length > 0) ||
          (first?.summary_csv && (typeof first.summary_csv.summary === 'string' && first.summary_csv.summary.trim().length > 0 || Array.isArray(first.summary_csv.summary) && first.summary_csv.summary.length > 0));
        const hasSummaryPdf =
          !!(first?.summary_pdf && ((typeof first.summary_pdf.summary === 'string' && first.summary_pdf.summary.trim().length > 0) || (first.summary_pdf.summary !== null && first.summary_pdf.summary !== undefined && first.summary_pdf.summary !== '')));

        if (!hasSummaryCsv && !hasSummaryPdf) {
          this.error = 'No results found. Try giving another query.';
          this.loading = false;
          this.cdr.markForCheck();
          return;
        }

        this.results = {
          disease_name: first?.disease_name ?? null,
          summary_pdf: first?.summary_pdf ?? null,
          summary_csv: rawCsv ?? null,
          summary_csv_raw: rawCsvString,
          related_images: Array.isArray(first?.related_images) ? first.related_images : [],
          details_chunks: first?.details_chunks ?? null,
          tests_details: normalizedTests as any,
        } as DetailItemExtended;

        console.debug('API summary_csv raw:', this.results?.summary_csv, 'summary_csv_raw:', this.results?.summary_csv_raw);

        this.resultMessage = `Results loaded for: "${trimmed}".`;
        this.loading = false;
        this.cdr.markForCheck();
      },
      error: (err: any) => {
        console.error('API error', err);
        if (err && err.message && err.message.startsWith('Request failed')) {
          this.error = 'Server rejected the request. Check console for details.';
        } else {
          this.error = err?.message ?? 'Something went wrong while fetching results.';
        }
        this.loading = false;
        this.cdr.markForCheck();
      },
    });
  }

  refresh(): void {
    this.router.navigateByUrl('/home');
  }

  get summaryPdfPages(): Array<string | number> {
    const pdf = (this.results?.summary_pdf as any) ?? null;
    const pages = pdf?.pages;

    if (!this.hasPdfSummary()) return [];

    if (Array.isArray(pages)) {
      return pages.map((p: any) => (typeof p === 'number' ? p : String(p)));
    }
    if (pages !== null && pages !== undefined) { return [String(pages)]; }
    return [];
  }

  hasPdfSummary(): boolean {
    const pdf = (this.results?.summary_pdf as any) ?? null;
    if (!pdf) return false;
    const s = pdf.summary;
    if (s === null || s === undefined) return false;
    if (this.isNilToken(s)) return false;
    const str = String(s).trim();
    return str.length > 0;
  }

  hasCsvSummary(): boolean {
    const raw = this.rawSummaryCsvString;
    if (raw && raw.trim().length > 0 && !this.isNilToken(raw)) return true;
    const lines = this.rawSummaryCsvLines;
    return Array.isArray(lines) && lines.length > 0;
  }

  toggleSqlModal(open?: boolean): void {
    this.showSqlModal = typeof open === 'boolean' ? open : !this.showSqlModal;
    try {
      if (this.showSqlModal) {
        document.body.classList.add('modal-open');
      } else {
        document.body.classList.remove('modal-open');
      }
    } catch (e) { }
    if (!this.showSqlModal) {
      this.clearCopyFeedback();
    }
    this.cdr.markForCheck();
  }

  async copySql(): Promise<void> {
    const text = (this.sqlCommand ?? '').trim();
    if (!text) return;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
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

  downloadSql(): void {
    const text = (this.sqlCommand ?? '').trim();
    if (!text) return;
    try {
      const blob = new Blob([text], { type: 'text/sql;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      const filename = 'query.sql';
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Download failed', err);
    }
  }

  trackByIndex(index: number, _item: any): number {
    return index;
  }

  private clearMessages(): void {
    this.error = null;
    this.resultMessage = null;
    this.results = null;
    this.sqlCommand = null;
    this.cdr.markForCheck();
  }

  private clearCopyFeedback(): void {
    this.showCopySuccess = false;
    if (this.copyTimer) {
      clearTimeout(this.copyTimer);
      this.copyTimer = null;
    }
  }

  ngOnDestroy(): void {
    if (this.apiSub) {
      this.apiSub.unsubscribe();
      this.apiSub = null;
    }
    if (this.copyTimer) {
      clearTimeout(this.copyTimer);
      this.copyTimer = null;
    }
    try {
      document.body.classList.remove('modal-open');
    } catch { }
  }

  get rawSummaryCsvString(): string | null {
    const s = (this.results as any)?.summary_csv_raw;
    if (typeof s === 'string' && s.trim().length && !this.isNilToken(s)) return s.trim();

    const maybe = this.results?.summary_csv?.summary;
    if (typeof maybe === 'string') {
      if (this.isNilToken(maybe)) return null;
      if (maybe.trim().length) return maybe.trim();
    }
    if (Array.isArray(maybe) && maybe.length) {
      const arr = maybe.map(String).filter(x => !this.isNilToken(x)).map(x => x.trim());
      return arr.length ? arr.join('\n') : null;
    }
    return null;
  }

  get rawSummaryCsvLines(): string[] {
    const raw = this.rawSummaryCsvString;
    if (!raw) return [];
    return raw
      .split(/\r?\n/)
      .map(function (l: string) {
        return (l || '').trim();
      })
      .filter(function (l: string) {
        return !!l;
      });
  }

  get summaryCsvAsArray(): string[] | null {
    const s = this.results?.summary_csv?.summary;
    if (Array.isArray(s)) {
      return s
        .filter((x: unknown): x is string => typeof x === 'string' && !(String(x).trim().toUpperCase() === 'NIL'))
        .map((x: string) => x.replace(/^["']+|["']+$/g, '').trim());
    }
    return null;
  }

  /** Parse the raw CSV-like summary into a heading and numbered items. */
/** Parse the raw CSV-like summary into a heading and numbered items. */
get parsedSummaryCsv(): { heading: string | null; items: string[]; numbered: boolean } {
  const raw = this.rawSummaryCsvString;
  if (!raw) return { heading: null, items: [], numbered: false };

  const colonIndex = raw.indexOf(':');
  const newlineIndex = raw.indexOf('\n');
  let heading: string | null = null;
  let rest = raw;

  if (colonIndex > -1) {
    heading = raw.slice(0, colonIndex).trim();
    rest = raw.slice(colonIndex + 1);
  } else if (newlineIndex > -1) {
    heading = raw.slice(0, newlineIndex).trim();
    rest = raw.slice(newlineIndex + 1);
  } else {
    const firstSentenceEnd = raw.indexOf('.') > -1 ? raw.indexOf('.') : -1;
    if (firstSentenceEnd > -1 && firstSentenceEnd < 80) {
      heading = raw.slice(0, firstSentenceEnd + 1).trim();
      rest = raw.slice(firstSentenceEnd + 1);
    }
  }

  // Normalize rest: collapse newlines to spaces for easier token detection
  rest = rest.replace(/\r?\n/g, ' ').trim();

  // Detect whether there is a whitespace (space/newline/tab) immediately before a numeric token
  // Examples that match: " 1.", "\n2)", " 3-"  — these indicate a numbered list we should split on.
  const hasWhitespaceBeforeNumber = /(^|\s)\d+[\.\)\-]?\s+/.test(rest);

  let items: string[] = [];

  if (hasWhitespaceBeforeNumber) {
    // Split on numeric tokens that are preceded by whitespace or start-of-string.
    // We remove the numeric tokens from the items (so the <ol> will supply markers).
    // Use a regex that finds number tokens like "1.", "2)", "3-" optionally followed by spaces.
    items = rest
      .split(/(?:^|\s)\d+[\.\)\-]?\s+/)
      .map(s => s.trim())
      .filter(Boolean);
  } else {
    // No whitespace before numbers — keep numbers as-is.
    // Try to split on common separators (commas, semicolons, bullets) or fallback to the whole rest.
    const splitCandidates = rest.split(/\s*[,;•]\s*/).map(s => s.trim()).filter(Boolean);
    items = splitCandidates.length ? splitCandidates : [rest];
  }

  return { heading: heading || null, items, numbered: hasWhitespaceBeforeNumber };
}


  get summaryCsvItems(): Array<{ title: string; desc: string }> | null {
    const raw = this.rawSummaryCsvString;
    if (!raw) return null;

    const normalized = raw.replace(/[–—]/g, '-').trim();

    const parts = normalized.split(/(?=\b\d+[\.\)\s-])/g).map(function (p) { return p.trim(); }).filter(function (p) { return !!p; });

    const items: Array<{ title: string; desc: string }> = [];

    for (const part of parts) {
      const withoutNum = part.replace(/^\d+[\.\)\s-]*/, '').trim();
      if (!withoutNum) continue;

      const sepIndex = withoutNum.indexOf('-');
      if (sepIndex > -1) {
        const title = withoutNum.slice(0, sepIndex).trim();
        const desc = withoutNum.slice(sepIndex + 1).trim();
        items.push({ title: this.cleanItemText(title), desc: this.cleanItemText(desc) });
        continue;
      }

      const altMatch = withoutNum.match(/(.*?)\s*[—–-]\s*(.*)/);
      if (altMatch) {
        items.push({ title: this.cleanItemText(altMatch[1]), desc: this.cleanItemText(altMatch[2]) });
        continue;
      }

      const commaSplit = withoutNum.split(/\s*,\s*/);
      if (commaSplit.length > 1) {
        items.push({ title: this.cleanItemText(commaSplit[0]), desc: this.cleanItemText(commaSplit.slice(1).join(', ')) });
        continue;
      }

      items.push({ title: '', desc: this.cleanItemText(withoutNum) });
    }

    return items.length ? items : null;
  }

  private cleanItemText(s: string): string {
    return String(s || '').replace(/^["']+|["']+$/g, '').trim();
  }

  get testsCards(): Array<{ score: number | null; names: string[] }> | null {
    const raw = this.results?.tests_details;
    if (!raw) return null;

    if (Array.isArray(raw)) {
      const cards = raw.map((entry: any) => {
        const score: number | null = typeof entry?.score === 'number' ? entry.score : null;
        const rawName = entry?.test_name ?? entry?.name ?? entry ?? null;
        const names = this.parseTestNames(rawName);
        return { score, names };
      });
      return cards.filter(c => Array.isArray(c.names) && c.names.length > 0);
    }

    if (typeof raw === 'string') {
      const names = this.parseTestNames(raw);
      return names.length ? [{ score: null, names }] : null;
    }

    return null;
  }

  parseTestNames(value: unknown): string[] {
    if (value === null || value === undefined) return [];

    if (Array.isArray(value)) {
      return value
        .filter((x: unknown): x is string => typeof x === 'string')
        .map((s: string) => s.replace(/^["']+|["']+$/g, '').trim());
    }

    if (typeof value === 'string') {
      const str = value.trim();

      if (str.startsWith('[') && str.endsWith(']')) {
        try {
          const normalized = str.replace(/(['"])?([a-zA-Z0-9\s\-\_\/\(\)]+)(['"])?(?=\s*,|\s*\])/g, '"$2"');
          const parsed = JSON.parse(normalized);
          if (Array.isArray(parsed)) {
            return parsed.map((s: any) => String(s).replace(/^["']+|["']+$/g, '').trim()).filter(Boolean);
          }
        } catch {
        }

        const items: string[] = [];
        const regex = /["']?([^"'\]]+?)["']?(?=(?:\s*,|\s*\]))/g;
        let m: RegExpExecArray | null;
        while ((m = regex.exec(str)) !== null) {
          const raw = m[1].trim();
          if (raw) items.push(raw.replace(/^["']+|["']+$/g, '').trim());
        }
        if (items.length) return items;
      }

      const splitCandidates = str.split(/\s*[,;•\n]\s*/).map(function (s) { return s.trim(); }).filter(function (s) { return !!s; });
      if (splitCandidates.length > 1) {
        return splitCandidates.map((s: string) => s.replace(/^["']+|["']+$/g, '').trim());
      }

      return [str.replace(/^["']+|["']+$/g, '').trim()];
    }

    return [String(value)];
  }

  openUserGuide(): void {
    try {
      const url = '/assets/images/MedIQ Smart Medical Intelligence Platform User Guide 2.pdf';
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
}
