export interface QuoteItem {
  label: string;
  qty: number;
  price: number;
  total?: number;
}

export interface Quote {
  id: number;
  number: string | null;
  lead_id: number | null;
  name: string | null;
  phone: string | null;
  address: string | null;
  job_type: string | null;
  items: QuoteItem[] | null;
  subtotal: number | null;
  tax_rate: number | null;
  total: number | null;
  status: string | null;
  notes: string | null;
  created_at: string | null;
  pdf_url: string | null;
}

export interface CreateQuoteRequest {
  lead_id?: number;
  name?: string;
  phone?: string;
  address?: string;
  job_type?: string;
  notes?: string;
  tax_rate?: number;
  items: { label: string; qty: number; price: number }[];
}
