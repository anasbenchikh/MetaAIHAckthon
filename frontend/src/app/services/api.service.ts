import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import { Appointment } from '../models/appointment.model';
import { Call } from '../models/call.model';
import { Lead } from '../models/lead.model';
import { CreateQuoteRequest, Quote } from '../models/quote.model';

export interface CreateQuoteResponse {
  success: boolean;
  quote: Quote;
}

export interface SendQuoteResponse {
  success: boolean;
  provider?: string;
  message_id?: string;
  message?: string;
  quote?: Quote;
}

export interface StatsSummary {
  month: string;
  calls: number;
  leads: number;
  appointments: number;
  accepted_quotes: number;
  accepted_revenue: number;
}

export interface PlaceCallResponse {
  success: boolean;
  provider?: string;
  external_call_id?: string;
  message?: string;
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly apiUrl = 'http://localhost:8000';

  getLeads(): Observable<Lead[]> {
    return this.http.get<Lead[]>(`${this.apiUrl}/leads`);
  }

  getAppointments(): Observable<Appointment[]> {
    return this.http.get<Appointment[]>(`${this.apiUrl}/appointments`);
  }

  getCalls(): Observable<Call[]> {
    return this.http.get<Call[]>(`${this.apiUrl}/calls`);
  }

  getQuotes(): Observable<Quote[]> {
    return this.http.get<Quote[]>(`${this.apiUrl}/quotes`);
  }

  createQuote(payload: CreateQuoteRequest): Observable<CreateQuoteResponse> {
    return this.http.post<CreateQuoteResponse>(`${this.apiUrl}/tools/create-quote`, payload);
  }

  sendQuote(quote_id: number): Observable<SendQuoteResponse> {
    return this.http.post<SendQuoteResponse>(`${this.apiUrl}/tools/send-quote`, {
      quote_id,
    });
  }

  quotePdfUrl(quote: Quote): string {
    return `${this.apiUrl}${quote.pdf_url}`;
  }

  setQuoteStatus(id: number, status: string): Observable<CreateQuoteResponse> {
    return this.http.patch<CreateQuoteResponse>(`${this.apiUrl}/quotes/${id}/status`, {
      status,
    });
  }

  getStats(): Observable<StatsSummary> {
    return this.http.get<StatsSummary>(`${this.apiUrl}/stats/summary`);
  }

  placeCall(to_number: string): Observable<PlaceCallResponse> {
    return this.http.post<PlaceCallResponse>(`${this.apiUrl}/tools/place-call`, {
      to_number,
    });
  }
}
