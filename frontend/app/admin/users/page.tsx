"use client";
import { Suspense, useEffect, useState } from "react";
import { users, type User } from "@/lib/api";
import { useApi, useDebounce } from "@/lib/hooks/useApi";
import { useListState } from "@/lib/hooks/useListState";
import { useAuth } from "@/lib/auth/AuthContext";
import { formatDateTime } from "@/lib/format";
import { Badge, FilterBar, Pagination, SearchInput, Select, type Column } from "@/components/ui";
import { CrudPage, clean, type FormField } from "@/components/domain/CrudPage";
import { ROLE_LABELS } from "@/lib/rbac";

const ROLES = ["admin", "sales_manager", "sales_rep", "finance", "customer"] as const;

function Inner() {
  const { state, set, page, setPage } = useListState();
  const { can } = useAuth();
  const [q, setQ] = useState(state.q ?? "");
  const debounced = useDebounce(q);
  useEffect(() => { if (debounced !== (state.q ?? "")) set({ q: debounced }); }, [debounced]); // eslint-disable-line react-hooks/exhaustive-deps
  const { data, error, loading, reload } = useApi(() => users.list({ q: state.q, role: state.role, is_active: state.is_active, page, page_size: 25 }), [JSON.stringify(state), page]);

  const columns: Column<User>[] = [
    { key: "name", header: "Name", render: (r) => <><span className="font-medium">{r.full_name}</span><span className="block text-xs text-zinc-500">{r.email}</span></> },
    { key: "role", header: "Role", render: (r) => <Badge tone={r.role === "admin" ? "purple" : r.role === "customer" ? "neutral" : "blue"}>{ROLE_LABELS[r.role as keyof typeof ROLE_LABELS] ?? r.role}</Badge> },
    { key: "team", header: "Team", render: (r) => r.team ?? "—" },
    { key: "status", header: "Status", render: (r) => <Badge tone={r.is_active ? "green" : "slate"}>{r.is_active ? "Active" : "Disabled"}</Badge> },
    { key: "last", header: "Last sign-in", render: (r) => formatDateTime(r.last_login_at) },
  ];

  const fields: FormField<User>[] = [
    { name: "full_name", label: "Full name", type: "text", required: true },
    { name: "email", label: "Email", type: "text", required: true, createOnly: true },
    { name: "role", label: "Role", type: "select", required: true, options: ROLES.map((r) => ({ value: r, label: ROLE_LABELS[r] })) },
    { name: "team", label: "Team", type: "text" },
    { name: "customer_id", label: "Linked customer id", type: "number", hint: "Required for portal (customer) accounts only." },
    { name: "password", label: "Password", type: "text", hint: "On edit, leave blank to keep the current password." },
    { name: "is_active", label: "Active", type: "checkbox" },
  ];

  return (
    <CrudPage
      config={{
        title: "Users",
        subtitle: "Accounts, roles and team assignment. Roles decide both navigation and API permissions.",
        addLabel: "+ New user",
        columns,
        fields,
        keyOf: (r) => r.id,
        canManage: can("user:manage"),
        toForm: (r) => ({ full_name: r.full_name, email: r.email, role: r.role, team: r.team ?? "", customer_id: r.customer_id ? String(r.customer_id) : "", password: "", is_active: String(r.is_active) }),
        toBody: (f) => clean({
          full_name: f.full_name,
          email: f.email,
          role: f.role,
          team: f.team,
          customer_id: f.customer_id ? Number(f.customer_id) : undefined,
          password: f.password,
          is_active: f.is_active === "true",
        }),
        create: (body) => users.create(body),
        update: (row, body) => users.update(row.id, body),
      }}
      defaults={{ role: "sales_rep", is_active: "true" }}
      rows={data?.items}
      loading={loading}
      error={error}
      reload={reload}
      filters={
        <FilterBar>
          <SearchInput value={q} onChange={setQ} placeholder="Name or email" className="w-72" />
          <Select value={state.role ?? ""} onChange={(e) => set({ role: e.target.value })} className="w-48" aria-label="Role">
            <option value="">All roles</option>
            {ROLES.map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
          </Select>
          <Select value={state.is_active ?? ""} onChange={(e) => set({ is_active: e.target.value })} className="w-40" aria-label="Status">
            <option value="">All</option>
            <option value="true">Active</option>
            <option value="false">Disabled</option>
          </Select>
        </FilterBar>
      }
      pagination={data ? <Pagination page={data.page} totalPages={data.total_pages} total={data.total} pageSize={data.page_size} onChange={setPage} /> : null}
    />
  );
}

export default function UsersPage() {
  return <Suspense><Inner /></Suspense>;
}
