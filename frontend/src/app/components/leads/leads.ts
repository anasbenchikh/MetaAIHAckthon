import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatIconModule } from '@angular/material/icon';
import { MatTableModule } from '@angular/material/table';
import { Lead } from '../../models/lead.model';
import { ApiService } from '../../services/api.service';
import { LanguageService } from '../../services/language.service';

@Component({
  selector: 'app-leads',
  imports: [CommonModule, MatButtonModule, MatCardModule, MatIconModule, MatTableModule],
  templateUrl: './leads.html',
  styleUrl: './leads.css',
})
export class Leads implements OnInit {
  private readonly api = inject(ApiService);
  protected readonly lang = inject(LanguageService);

  protected readonly leads = signal<Lead[]>([]);
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly notice = signal<string | null>(null);
  protected readonly columns = ['name', 'phone', 'job_type', 'urgency', 'created_at', 'actions'];
  protected readonly subtitle = computed(() =>
    this.lang.t('leads.subtitle').replace('{n}', String(this.leads().length)),
  );

  ngOnInit(): void {
    this.api.getLeads().subscribe({
      next: (leads) => {
        this.leads.set(leads);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.error.set(this.lang.t('common.apiError'));
      },
    });
  }

  protected urgencyLevel(urgency: string | null): string {
    return (urgency ?? '').trim().toLowerCase();
  }

  protected call(phone: string | null): void {
    this.notice.set(null);
    if (!phone) {
      this.error.set(this.lang.t('leads.noPhone'));
      return;
    }
    this.api.placeCall(phone).subscribe({
      next: () => {
        this.error.set(null);
        this.notice.set(this.lang.t('leads.called').replace('{p}', phone));
      },
      error: (err: HttpErrorResponse) =>
        this.error.set(this.lang.t('leads.callError') + (err.error?.message || '')),
    });
  }
}
