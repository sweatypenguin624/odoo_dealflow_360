"use client";
import { ReactNode, useState } from "react";
import { errorMessage } from "@/lib/api/client";
import { Button, Card, DataTable, ErrorState, Field, FormError, Input, Modal, PageHeader, Select, Textarea, type Column } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";

export type FieldType = "text" | "number" | "date" | "select" | "checkbox" | "textarea" | "custom";

export interface FormField<T> {
  name: string;
  label: string;
  type: FieldType;
  required?: boolean;
  hint?: string;
  options?: { value: string | number; label: string }[];
  step?: string;
  min?: number;
  max?: number;
  /** Hidden (and not submitted) when editing — e.g. immutable scope keys. */
  createOnly?: boolean;
  full?: boolean;
  render?: (value: string, set: (v: string) => void, row: T | null) => ReactNode;
}

export interface CrudConfig<T> {
  title: string;
  subtitle?: string;
  addLabel?: string;
  columns: Column<T>[];
  fields: FormField<T>[];
  keyOf: (row: T) => string | number;
  /** Map an existing row to form values for editing. */
  toForm: (row: T) => Record<string, string>;
  /** Turn form values into the request body; return null to abort. */
  toBody: (form: Record<string, string>, isEdit: boolean) => Record<string, unknown>;
  create?: (body: Record<string, unknown>) => Promise<unknown>;
  update?: (row: T, body: Record<string, unknown>) => Promise<unknown>;
  emptyTitle?: string;
  canManage: boolean;
}

/**
 * Table + create/edit modal shared by the admin reference-data screens. Each
 * page supplies its columns, fields and request mapping; validation messages
 * always come from the API.
 */
export function CrudPage<T>({
  config,
  rows,
  loading,
  error,
  reload,
  filters,
  pagination,
  defaults = {},
}: {
  config: CrudConfig<T>;
  rows: T[] | undefined;
  loading: boolean;
  error: string | null;
  reload: () => void;
  filters?: ReactNode;
  pagination?: ReactNode;
  defaults?: Record<string, string>;
}) {
  const toast = useToast();
  const [editing, setEditing] = useState<T | null>(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function openCreate() {
    setEditing(null);
    setForm({ ...defaults });
    setFormError(null);
    setOpen(true);
  }

  function openEdit(row: T) {
    if (!config.canManage || !config.update) return;
    setEditing(row);
    setForm(config.toForm(row));
    setFormError(null);
    setOpen(true);
  }

  async function save() {
    setBusy(true);
    setFormError(null);
    try {
      const body = config.toBody(form, editing !== null);
      if (editing) await config.update?.(editing, body);
      else await config.create?.(body);
      toast.success(editing ? `${config.title} updated.` : `${config.title} created.`);
      setOpen(false);
      reload();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  const set = (name: string) => (value: string) => setForm((f) => ({ ...f, [name]: value }));
  const visibleFields = config.fields.filter((f) => !(editing && f.createOnly));

  return (
    <div className="space-y-4">
      <PageHeader
        title={config.title}
        subtitle={config.subtitle}
        actions={config.canManage && config.create && <Button onClick={openCreate}>{config.addLabel ?? `+ New ${config.title.replace(/s$/, "").toLowerCase()}`}</Button>}
      />
      {filters}
      {error && <ErrorState message={error} onRetry={reload} />}
      <DataTable
        columns={config.columns}
        rows={rows}
        keyOf={config.keyOf}
        loading={loading}
        onRowClick={config.canManage && config.update ? openEdit : undefined}
        emptyTitle={config.emptyTitle ?? "Nothing configured yet"}
      />
      {pagination}

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={editing ? `Edit ${config.title.replace(/s$/, "").toLowerCase()}` : (config.addLabel ?? `New ${config.title.replace(/s$/, "").toLowerCase()}`)}
        size="lg"
        footer={<><Button variant="secondary" onClick={() => setOpen(false)} disabled={busy}>Cancel</Button><Button onClick={save} loading={busy}>{editing ? "Save changes" : "Create"}</Button></>}
      >
        <div className="space-y-3">
          <FormError message={formError} />
          <div className="grid gap-3 sm:grid-cols-2">
            {visibleFields.map((f) => {
              const value = form[f.name] ?? "";
              if (f.type === "checkbox") {
                return (
                  <label key={f.name} className={`flex items-center gap-2 text-sm text-zinc-700 ${f.full ? "sm:col-span-2" : ""}`}>
                    <input type="checkbox" className="h-4 w-4 rounded border-zinc-300 text-blue-600 focus:ring-blue-500" checked={value === "true"} onChange={(e) => set(f.name)(String(e.target.checked))} />
                    {f.label}
                  </label>
                );
              }
              return (
                <Field key={f.name} label={f.label} required={f.required} hint={f.hint} className={f.full ? "sm:col-span-2" : ""}>
                  {f.type === "custom" && f.render ? f.render(value, set(f.name), editing)
                    : f.type === "select" ? (
                      <Select value={value} onChange={(e) => set(f.name)(e.target.value)}>
                        {!f.required && <option value="">—</option>}
                        {f.options?.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                      </Select>
                    ) : f.type === "textarea" ? (
                      <Textarea rows={3} value={value} onChange={(e) => set(f.name)(e.target.value)} />
                    ) : (
                      <Input type={f.type} step={f.step} min={f.min} max={f.max} value={value} onChange={(e) => set(f.name)(e.target.value)} />
                    )}
                </Field>
              );
            })}
          </div>
        </div>
      </Modal>
    </div>
  );
}

/** Strips empty strings so optional fields are omitted rather than sent as "". */
export function clean(body: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(body)) {
    if (v !== "" && v !== undefined) out[k] = v;
  }
  return out;
}

export { Card };
