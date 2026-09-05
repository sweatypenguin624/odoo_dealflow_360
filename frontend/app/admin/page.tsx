import Link from "next/link";

export default function AdminPage() {
  return (
    <div className="mx-auto flex min-h-screen max-w-2xl flex-col items-start justify-center gap-4 px-4">
      <h1 className="text-2xl font-semibold text-zinc-900 dark:text-zinc-50">Back-end Admin</h1>
      <p className="text-zinc-600 dark:text-zinc-400">
        This is a placeholder. There is no real admin UI in this phase - warehouses, subscription
        plans, and product pairings are managed via the API directly (see the backend routers under{" "}
        <code className="rounded bg-zinc-100 px-1 py-0.5 dark:bg-zinc-800">backend/app/routers/</code>
        ).
      </p>
      <Link href="/workspace/quotations" className="text-blue-600 hover:underline dark:text-blue-400">
        Back to the workspace
      </Link>
    </div>
  );
}
