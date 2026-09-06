"use client";
import { useState } from "react";
import { settings, type Setting } from "@/lib/api";
import { errorMessage } from "@/lib/api/client";
import { useApi } from "@/lib/hooks/useApi";
import { formatDateTime, titleCase } from "@/lib/format";
import { Button, Card, ErrorState, Input, PageHeader, Select, Skeleton } from "@/components/ui";
import { useToast } from "@/components/ui/Toast";

function SettingRow({ setting, onSaved }: { setting: Setting; onSaved: () => void }) {
  const toast = useToast();
  const [value, setValue] = useState(String(setting.value));
  const [busy, setBusy] = useState(false);
  const dirty = value !== String(setting.value);
  const isBool = setting.value_type === "bool" || setting.value_type === "boolean";
  const isNumber = setting.value_type === "int" || setting.value_type === "float" || setting.value_type === "number" || setting.value_type === "decimal";

  async function save() {
    setBusy(true);
    try {
      const parsed = isBool ? value === "true" : isNumber ? Number(value) : value;
      await settings.update(setting.key, parsed);
      toast.success(`${setting.key} updated.`);
      onSaved();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-wrap items-end justify-between gap-3 border-b border-zinc-100 py-3 last:border-0">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-zinc-900">{titleCase(setting.key)}</p>
        <p className="text-xs text-zinc-500">{setting.description}</p>
        <p className="mt-0.5 text-xs text-zinc-400">
          Default: <code className="kbd">{String(setting.default)}</code>
          {setting.updated_at ? ` · last changed ${formatDateTime(setting.updated_at)}` : " · never changed"}
        </p>
      </div>
      <div className="flex items-end gap-2">
        {isBool ? (
          <Select value={value} onChange={(e) => setValue(e.target.value)} className="w-32" aria-label={setting.key}>
            <option value="true">Enabled</option>
            <option value="false">Disabled</option>
          </Select>
        ) : (
          <Input type={isNumber ? "number" : "text"} step="any" value={value} onChange={(e) => setValue(e.target.value)} className="w-48" aria-label={setting.key} />
        )}
        <Button size="sm" onClick={save} loading={busy} disabled={!dirty}>Save</Button>
        {dirty && <Button size="sm" variant="ghost" onClick={() => setValue(String(setting.value))}>Reset</Button>}
      </div>
    </div>
  );
}

export default function SettingsPage() {
  const { data, error, loading, reload } = useApi(() => settings.list(), []);

  return (
    <div className="space-y-4">
      <PageHeader
        title="System Settings"
        subtitle="Behaviour shared across the platform. Changes apply to new evaluations immediately."
      />
      {error && <ErrorState message={error} onRetry={reload} />}
      {loading && !data && <Skeleton className="h-64" />}
      {data && (
        <Card>
          {data.map((s) => <SettingRow key={s.key} setting={s} onSaved={reload} />)}
        </Card>
      )}
    </div>
  );
}
