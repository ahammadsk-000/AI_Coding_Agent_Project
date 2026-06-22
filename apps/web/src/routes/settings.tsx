import { useState, type FormEvent } from "react";
import { Settings as SettingsIcon, KeyRound } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
import { initials } from "@/lib/utils";

export function SettingsPage() {
  const user = useAuthStore((s) => s.user);

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setDone(false);
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);
    try {
      await api.updateProfile({ password });
      setDone(true);
      setPassword("");
      setConfirm("");
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Unexpected error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="max-w-lg space-y-6">
      <header className="space-y-1">
        <div className="flex items-center gap-2.5">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-slate-400 to-slate-600 shadow-md">
            <SettingsIcon className="h-5 w-5 text-white" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        </div>
        <p className="text-sm text-muted-foreground">Manage your account.</p>
      </header>

      {/* account card */}
      <div className="flex items-center gap-3 rounded-xl border border-border bg-card/60 p-4 backdrop-blur">
        <div className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-gradient-to-br from-sky-400 to-indigo-500 text-sm font-semibold text-white">
          {initials(user?.full_name || user?.email || "?")}
        </div>
        <div className="min-w-0">
          <div className="truncate font-medium">{user?.full_name || "Account"}</div>
          <div className="truncate text-sm text-muted-foreground">{user?.email ?? "—"}</div>
        </div>
      </div>

      {/* change password card */}
      <div className="rounded-xl border border-border bg-card/60 p-5 backdrop-blur">
        <div className="mb-4 flex items-center gap-2">
          <KeyRound className="h-4 w-4 text-primary" />
          <h2 className="font-medium">Change password</h2>
        </div>
        <p className="mb-4 text-xs text-muted-foreground">
          Choose a new password (at least 8 characters). You'll use it the next
          time you sign in.
        </p>
        <form onSubmit={handleSubmit} className="space-y-3">
          <Input
            type="password"
            placeholder="New password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
          />
          <Input
            type="password"
            placeholder="Confirm new password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            minLength={8}
            autoComplete="new-password"
          />
          {error ? (
            <div
              className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
              role="alert"
            >
              {error}
            </div>
          ) : null}
          {done ? (
            <div
              className="rounded-md border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-500"
              role="status"
            >
              Password updated. Use it next time you sign in.
            </div>
          ) : null}
          <Button
            type="submit"
            loading={loading}
            className="bg-gradient-to-r from-sky-500 to-indigo-500"
          >
            Update password
          </Button>
        </form>
      </div>
    </div>
  );
}
