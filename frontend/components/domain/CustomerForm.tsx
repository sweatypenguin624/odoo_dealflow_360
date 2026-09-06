"use client";
import { useEffect, useState } from "react";
import { catalog, customers, users, type CustomerDetail, type Tier, type User } from "@/lib/api";
import { errorMessage } from "@/lib/api/client";
import { useAuth } from "@/lib/auth/AuthContext";
import { Button, Field, FormError, Input, Modal, Select, Textarea } from "@/components/ui";

const EMPTY = { name: "", tier_id: "", owner_user_id: "", industry: "", email: "", phone: "", website: "", contact_name: "", payment_terms_days: "30", currency: "USD", billing_address_line1: "", billing_city: "", billing_state: "", billing_postal_code: "", billing_country: "", shipping_address_line1: "", shipping_city: "", shipping_state: "", shipping_postal_code: "", shipping_country: "", notes: "" };

export function CustomerFormModal({ open, onClose, onSaved, initial }: { open: boolean; onClose: () => void; onSaved: (c: CustomerDetail) => void; initial?: CustomerDetail | null }) {
  const { user } = useAuth();
  const [form, setForm] = useState<Record<string, string>>(EMPTY);
  const [tiers, setTiers] = useState<Tier[]>([]);
  const [reps, setReps] = useState<User[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Reference data is fetched from an effect; the form itself is reset during
  // render when the dialog opens (React's "adjust state on prop change").
  const [wasOpen, setWasOpen] = useState(open);
  if (open !== wasOpen) {
    setWasOpen(open);
    if (open) {
      setForm(initial ? Object.fromEntries(Object.keys(EMPTY).map((k) => [k, initial[k as keyof CustomerDetail] == null ? "" : String(initial[k as keyof CustomerDetail])])) : EMPTY);
      setError(null);
    }
  }
  useEffect(() => {
    if (!open) return;
    catalog.tiers().then(setTiers).catch(() => undefined);
    if (user?.role !== "sales_rep") users.reps().then(setReps).catch(() => undefined);
  }, [open, user?.role]);
  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function save() {
    setBusy(true); setError(null);
    const body: Record<string, unknown> = { ...form, tier_id: Number(form.tier_id), owner_user_id: form.owner_user_id ? Number(form.owner_user_id) : undefined, payment_terms_days: Number(form.payment_terms_days) };
    for (const k of Object.keys(body)) if (body[k] === "") body[k] = undefined;
    try {
      const saved = initial ? await customers.update(initial.id, body) : await customers.create(body);
      onSaved(saved);
    } catch (err) { setError(errorMessage(err)); } finally { setBusy(false); }
  }
  const text = (k: string, label: string, type = "text", req = false) => <Field label={label} required={req}><Input type={type} value={form[k]} onChange={set(k)} required={req} /></Field>;
  return (
    <Modal open={open} onClose={onClose} title={initial ? "Edit customer" : "New customer"} size="lg" footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button onClick={save} loading={busy} disabled={!form.name || !form.tier_id}>{initial ? "Save changes" : "Create customer"}</Button></>}>
      <FormError message={error} />
      <div className="grid gap-3 sm:grid-cols-2">
        {text("name", "Company name", "text", true)}
        <Field label="Tier" required><Select value={form.tier_id} onChange={set("tier_id")}><option value="">Select tier…</option>{tiers.map((t) => <option key={t.id} value={t.id}>{t.name} (max {t.max_discount_pct}%)</option>)}</Select></Field>
        {user?.role !== "sales_rep" && <Field label="Account owner"><Select value={form.owner_user_id} onChange={set("owner_user_id")}><option value="">Unassigned</option>{reps.map((r) => <option key={r.id} value={r.id}>{r.full_name}</option>)}</Select></Field>}
        {text("industry", "Industry")}{text("contact_name", "Primary contact")}{text("email", "Contact email", "email")}{text("phone", "Phone")}{text("website", "Website")}
        {text("payment_terms_days", "Payment terms (days)", "number")}{text("currency", "Currency")}
        <p className="sm:col-span-2 text-xs font-semibold uppercase text-zinc-500">Billing address</p>
        {text("billing_address_line1", "Street")}{text("billing_city", "City")}{text("billing_state", "State")}{text("billing_postal_code", "Postal code")}{text("billing_country", "Country")}
        <p className="sm:col-span-2 text-xs font-semibold uppercase text-zinc-500">Shipping address</p>
        {text("shipping_address_line1", "Street")}{text("shipping_city", "City")}{text("shipping_state", "State")}{text("shipping_postal_code", "Postal code")}{text("shipping_country", "Country")}
        <Field label="Notes" className="sm:col-span-2"><Textarea rows={2} value={form.notes} onChange={set("notes")} /></Field>
      </div>
    </Modal>
  );
}
