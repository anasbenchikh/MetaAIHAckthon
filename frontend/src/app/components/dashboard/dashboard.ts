import { CommonModule } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { forkJoin, interval, startWith, switchMap } from 'rxjs';
import { Appointment } from '../../models/appointment.model';
import { Call } from '../../models/call.model';
import { Lead } from '../../models/lead.model';
import { ApiService, StatsSummary } from '../../services/api.service';
import { LanguageService } from '../../services/language.service';

const REVENUE_BY_URGENCY: Record<string, number> = {
  emergency: 600,
  urgent: 350,
  routine: 180,
};

@Component({
  selector: 'app-dashboard',
  imports: [CommonModule, MatButtonModule, MatCardModule, MatExpansionModule, MatIconModule, RouterLink],
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.css',
})
export class Dashboard implements OnInit {
  private readonly api = inject(ApiService);
  private readonly destroyRef = inject(DestroyRef);
  protected readonly lang = inject(LanguageService);

  protected readonly leads = signal<Lead[]>([]);
  protected readonly appointments = signal<Appointment[]>([]);
  protected readonly calls = signal<Call[]>([]);
  protected readonly error = signal<string | null>(null);
  protected readonly notice = signal<string | null>(null);
  protected readonly stats = signal<StatsSummary | null>(null);
  protected readonly updatedAt = signal<Date | null>(null);
  protected readonly revenue = computed(() =>
    this.leads().reduce(
      (sum, lead) => sum + (REVENUE_BY_URGENCY[(lead.urgency ?? '').toLowerCase()] ?? 0),
      0,
    ),
  );
  protected readonly recentLeads = computed(() => this.leads().slice(0, 5));
  protected readonly upcomingAppointments = computed(() =>
    [...this.appointments()]
      .sort((a, b) => (a.appointment_time ?? '').localeCompare(b.appointment_time ?? ''))
      .slice(0, 5),
  );
  protected readonly recentCalls = computed(() => this.calls().slice(0, 5));

  ngOnInit(): void {
    interval(5000)
      .pipe(
        startWith(0),
        switchMap(() =>
          forkJoin({
            leads: this.api.getLeads(),
            appointments: this.api.getAppointments(),
            calls: this.api.getCalls(),
            stats: this.api.getStats(),
          }),
        ),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe({
        next: ({ leads, appointments, calls, stats }) => {
          this.leads.set(leads);
          this.appointments.set(appointments);
          this.calls.set(calls);
          this.stats.set(stats);
          this.updatedAt.set(new Date());
          this.error.set(null);
        },
        error: () => this.error.set(this.lang.t('common.apiError')),
      });
  }

  protected urgencyLevel(urgency: string | null): string {
    return (urgency ?? '').trim().toLowerCase();
  }

  protected recall(phone: string | null): void {
    this.notice.set(null);
    if (!phone) {
      this.error.set(this.lang.t('dash.noPhone'));
      return;
    }
    this.api.placeCall(phone).subscribe({
      next: () => {
        this.error.set(null);
        this.notice.set(this.lang.t('dash.called').replace('{p}', phone));
      },
      error: (err: HttpErrorResponse) =>
        this.error.set(this.lang.t('dash.callError') + (err.error?.message || '')),
    });
  }

  protected callSummary(call: { summary: string | null; transcript: string | null }): string {
    return (call.summary || call.transcript || '').trim();
  }

  protected leadSentence(text: string): string {
    const match = text.match(/^.*?[.!?](\s|$)/);
    return (match ? match[0] : text).trim().slice(0, 200);
  }

  protected restSentence(text: string): string {
    const lead = this.leadSentence(text);
    return text.slice(lead.length).trim().slice(0, 160);
  }
}
