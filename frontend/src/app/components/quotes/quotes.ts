import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { Lead } from '../../models/lead.model';
import { CreateQuoteRequest, Quote } from '../../models/quote.model';
import { ApiService } from '../../services/api.service';
import { LanguageService } from '../../services/language.service';

interface ItemRow {
  label: string;
  qty: number | null;
  price: number | null;
}

@Component({
  selector: 'app-quotes',
  imports: [CommonModule, FormsModule, MatCardModule, MatTableModule, MatButtonModule, MatIconModule],
  templateUrl: './quotes.html',
  styleUrl: './quotes.css',
})
export class Quotes implements OnInit {
  protected readonly api = inject(ApiService);
  protected readonly lang = inject(LanguageService);

  protected readonly quotes = signal<Quote[]>([]);
  protected readonly leads = signal<Lead[]>([]);
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly notice = signal<string | null>(null);
  protected readonly columns = ['number', 'name', 'total', 'status', 'created_at', 'actions'];

  protected leadId: string = '';
  protected name = '';
  protected phone = '';
  protected address = '';
  protected job_type = '';
  protected notes = '';
  protected rows: ItemRow[] = [this.emptyRow()];

  protected readonly formTotal = computed(() =>
    this.rows.reduce((sum, row) => sum + (row.qty ?? 0) * (row.price ?? 0), 0),
  );

  ngOnInit(): void {
    this.api.getQuotes().subscribe({
      next: (quotes) => {
        this.quotes.set(quotes);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.error.set(this.lang.t('quotes.loadError'));
      },
    });
    this.api.getLeads().subscribe({
      next: (leads) => this.leads.set(leads),
      error: () => undefined,
    });
  }

  onLeadSelect(): void {
    const lead = this.leads().find((item) => String(item.id) === this.leadId);
    if (!lead) {
      return;
    }
    this.name = lead.name ?? '';
    this.phone = lead.phone ?? '';
    this.address = lead.address ?? '';
    this.job_type = lead.job_type ?? '';
  }

  addRow(): void {
    this.rows.push(this.emptyRow());
  }

  removeRow(index: number): void {
    if (this.rows.length > 1) {
      this.rows.splice(index, 1);
    }
  }

  submit(): void {
    this.error.set(null);
    this.notice.set(null);
    const items = this.rows
      .filter((row) => row.label.trim() && (row.qty ?? 0) > 0)
      .map((row) => ({ label: row.label.trim(), qty: row.qty ?? 0, price: row.price ?? 0 }));
    if (items.length === 0) {
      this.error.set(this.lang.t('quotes.needLine'));
      return;
    }
    const payload: CreateQuoteRequest = {
      lead_id: this.leadId ? Number(this.leadId) : undefined,
      name: this.name.trim() || undefined,
      phone: this.phone.trim() || undefined,
      address: this.address.trim() || undefined,
      job_type: this.job_type.trim() || undefined,
      notes: this.notes.trim() || undefined,
      items,
    };
    this.api.createQuote(payload).subscribe({
      next: (res) => {
        this.quotes.update((list) => [res.quote, ...list]);
        this.resetForm();
        this.notice.set(this.lang.t('quotes.created').replace('{n}', res.quote.number ?? ''));
      },
      error: (err: HttpErrorResponse) =>
        this.error.set(err.error?.message || this.lang.t('quotes.createError')),
    });
  }

  send(quote: Quote): void {
    this.error.set(null);
    this.notice.set(null);
    this.api.sendQuote(quote.id).subscribe({
      next: (res) => {
        this.quotes.update((list) =>
          list.map((q) => (q.id === quote.id ? { ...q, status: 'sent' } : q)),
        );
        this.notice.set(
          this.lang.t('quotes.sent')
            .replace('{n}', quote.number ?? '')
            .replace('{p}', res.provider ?? ''),
        );
      },
      error: (err: HttpErrorResponse) =>
        this.error.set(err.error?.message || this.lang.t('quotes.sendError')),
    });
  }

  setStatus(quote: Quote, status: string): void {
    this.error.set(null);
    this.notice.set(null);
    this.api.setQuoteStatus(quote.id, status).subscribe({
      next: (res) => {
        if (res.quote) {
          this.quotes.update((list) =>
            list.map((q) => (q.id === quote.id ? { ...q, status: res.quote!.status } : q)),
          );
        }
        this.notice.set(this.lang.t('quotes.statusSet'));
      },
      error: (err: HttpErrorResponse) =>
        this.error.set(err.error?.message || this.lang.t('quotes.statusError')),
    });
  }

  statusLevel(status: string | null): string {
    if (status === 'accepted' || status === 'sent') return 'routine';
    if (status === 'refused') return 'emergency';
    return '';
  }

  private emptyRow(): ItemRow {
    return { label: '', qty: 1, price: null };
  }

  private resetForm(): void {
    this.leadId = '';
    this.name = '';
    this.phone = '';
    this.address = '';
    this.job_type = '';
    this.notes = '';
    this.rows = [this.emptyRow()];
  }
}
