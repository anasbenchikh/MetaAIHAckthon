export interface Call {
  id: number;
  retell_call_id: string;
  from_number: string | null;
  transcript: string | null;
  summary: string | null;
  status: string | null;
  created_at: string | null;
}
