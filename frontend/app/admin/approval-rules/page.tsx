"use client";
import { pricing, type ApprovalRule } from "@/lib/api";
import { errorMessage } from "@/lib/api/client";
import { useApi } from "@/lib/hooks/useApi";
import { useAuth } from "@/lib/auth/AuthContext";
import { formatCurrency, formatDate } from "@/lib/format";
import { Badge, Button, Card, type Column } from "@/components/ui";
import { CrudPage, clean, type FormField } from "@/components/domain/CrudPage";
import { useToast } from "@/components/ui/Toast";

export default function ApprovalRulesPage() {
  const { can } = useAuth();
  const toast = useToast();
  const { data, error, loading, reload } = useApi(() => pricing.approvalRules(), []);
  const policy = useApi(() => pricing.policy(), []);
  const manage = can("approval_rules:manage");

  async function remove(rule: ApprovalRule) {
    try {
      await pricing.deleteApprovalRule(rule.id);
      toast.success("Rule deleted.");
      reload();
      policy.reload();
    } catch (err) {
      toast.error(errorMessage(err));
    }
  }

  const columns: Column<ApprovalRule>[] = [
    { key: "name", header: "Rule", render: (r) => <span className="font-medium">{r.name}</span> },
    { key: "level", header: "Routes to", render: (r) => <Badge tone={r.approval_level === "manager" ? "amber" : "red"}>{r.approval_level === "manager" ? "Manager" : "Manager → Finance"}</Badge> },
    { key: "points", header: "Min points over", align: "right", render: (r) => `${Number(r.min_points_over).toFixed(1)} pts` },
    { key: "excess", header: "Min excess amount", align: "right", render: (r) => r.min_excess_amount === null ? <span className="text-zinc-400">Any</span> : formatCurrency(r.min_excess_amount) },
    { key: "expiry", header: "Request expiry", align: "right", render: (r) => r.expires_after_days ? `${r.expires_after_days} d` : "—" },
    { key: "validity", header: "Valid", render: (r) => <span className="text-xs">{r.valid_from || r.valid_to ? `${formatDate(r.valid_from)} – ${formatDate(r.valid_to)}` : "Always"}</span> },
    { key: "status", header: "Status", render: (r) => <Badge tone={r.is_active ? "green" : "slate"}>{r.is_active ? "Active" : "Inactive"}</Badge> },
    { key: "actions", header: "", render: (r) => manage ? <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); remove(r); }}>Delete</Button> : null },
  ];

  const fields: FormField<ApprovalRule>[] = [
    { name: "name", label: "Rule name", type: "text", required: true },
    { name: "approval_level", label: "Routes to", type: "select", required: true, options: [{ value: "manager", label: "Manager" }, { value: "manager_then_finance", label: "Manager, then Finance" }] },
    { name: "min_points_over", label: "Min points over limit", type: "number", required: true, step: "0.5", min: 0, max: 100, hint: "How far past the allowed discount a line must be before this rule applies." },
    { name: "min_excess_amount", label: "Min excess amount", type: "number", step: "0.01", min: 0, hint: "Optional currency floor. Leave blank to apply at any amount." },
    { name: "expires_after_days", label: "Request expires after (days)", type: "number", min: 1 },
    { name: "valid_from", label: "Valid from", type: "date" },
    { name: "valid_to", label: "Valid to", type: "date" },
    { name: "is_active", label: "Active", type: "checkbox" },
  ];

  return (
    <div className="space-y-4">
      <CrudPage
        config={{
          title: "Approval Rules",
          subtitle: "Thresholds the risk engine uses to decide whether a quotation needs manager or finance sign-off.",
          addLabel: "+ New rule",
          columns,
          fields,
          keyOf: (r) => r.id,
          canManage: manage,
          toForm: (r) => ({
            name: r.name, approval_level: r.approval_level, min_points_over: String(r.min_points_over),
            min_excess_amount: r.min_excess_amount === null ? "" : String(r.min_excess_amount),
            expires_after_days: r.expires_after_days ? String(r.expires_after_days) : "",
            valid_from: r.valid_from ?? "", valid_to: r.valid_to ?? "", is_active: String(r.is_active),
          }),
          toBody: (f, isEdit) => {
            const body = clean({
              name: f.name,
              approval_level: f.approval_level,
              min_points_over: Number(f.min_points_over),
              min_excess_amount: f.min_excess_amount === "" ? undefined : Number(f.min_excess_amount),
              expires_after_days: f.expires_after_days === "" ? undefined : Number(f.expires_after_days),
              valid_from: f.valid_from,
              valid_to: f.valid_to,
              is_active: f.is_active === "true",
            });
            if (isEdit && f.min_excess_amount === "") body.clear_min_excess_amount = true;
            return body;
          },
          create: (body) => pricing.createApprovalRule(body),
          update: (row, body) => pricing.updateApprovalRule(row.id, body),
        }}
        defaults={{ approval_level: "manager", is_active: "true" }}
        rows={data ?? undefined}
        loading={loading}
        error={error}
        reload={() => { reload(); policy.reload(); }}
      />

      {policy.data && (
        <Card title="Effective policy">
          <p className="text-sm text-zinc-600">
            Derived from the active rules above — this is what the risk engine applies right now.
          </p>
          <dl className="mt-2 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div><dt className="text-xs uppercase text-zinc-500">Manager threshold</dt><dd className="font-medium">{Number(policy.data.manager_threshold).toFixed(1)} pts</dd></div>
            <div><dt className="text-xs uppercase text-zinc-500">Finance threshold</dt><dd className="font-medium">{Number(policy.data.finance_threshold).toFixed(1)} pts</dd></div>
            <div><dt className="text-xs uppercase text-zinc-500">Manager excess floor</dt><dd className="font-medium">{policy.data.manager_excess_amount === null ? "Any" : formatCurrency(policy.data.manager_excess_amount)}</dd></div>
            <div><dt className="text-xs uppercase text-zinc-500">Finance excess floor</dt><dd className="font-medium">{policy.data.finance_excess_amount === null ? "Any" : formatCurrency(policy.data.finance_excess_amount)}</dd></div>
          </dl>
        </Card>
      )}
    </div>
  );
}
