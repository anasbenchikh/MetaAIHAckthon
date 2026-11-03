import { CommonModule } from '@angular/common';
import { Component, OnInit, computed, inject, signal, viewChild } from '@angular/core';
import { MatCalendar, MatDatepickerModule } from '@angular/material/datepicker';
import { MatCardModule } from '@angular/material/card';
import { MatTableModule } from '@angular/material/table';
import { Appointment } from '../../models/appointment.model';
import { ApiService } from '../../services/api.service';
import { LanguageService } from '../../services/language.service';

@Component({
  selector: 'app-appointments',
  imports: [CommonModule, MatCardModule, MatDatepickerModule, MatTableModule],
  templateUrl: './appointments.html',
  styleUrl: './appointments.css',
})
export class Appointments implements OnInit {
  private readonly api = inject(ApiService);
  private readonly calendar = viewChild.required(MatCalendar);
  protected readonly lang = inject(LanguageService);

  protected readonly appointments = signal<Appointment[]>([]);
  protected readonly loading = signal(true);
  protected readonly error = signal<string | null>(null);
  protected readonly selected = signal<Date>(new Date());
  protected readonly columns = ['name', 'phone', 'job_type', 'address', 'appointment_time'];
  protected readonly selectedDayAppointments = computed(() => {
    const key = this.dayKey(this.selected());
    return this.appointments().filter((appt) => this.apptDayKey(appt) === key);
  });
  protected readonly subtitle = computed(() =>
    this.lang.t('appts.subtitle').replace('{n}', String(this.appointments().length)),
  );

  ngOnInit(): void {
    this.api.getAppointments().subscribe({
      next: (appointments) => {
        this.appointments.set(appointments);
        this.loading.set(false);
        this.calendar().updateTodaysDate();
      },
      error: () => {
        this.loading.set(false);
        this.error.set(this.lang.t('common.apiError'));
      },
    });
  }

  protected onSelect(date: Date | null): void {
    if (date) {
      this.selected.set(date);
    }
  }

  protected dateClass = (date: Date, view: 'month' | 'year' | 'multi-year'): string => {
    if (view !== 'month') {
      return '';
    }
    const key = this.dayKey(date);
    return this.appointments().some((appt) => this.apptDayKey(appt) === key)
      ? 'booked-day'
      : '';
  };

  private dayKey(date: Date): string {
    return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
  }

  private apptDayKey(appt: Appointment): string {
    if (!appt.appointment_time) {
      return '';
    }
    return this.dayKey(new Date(appt.appointment_time));
  }
}
