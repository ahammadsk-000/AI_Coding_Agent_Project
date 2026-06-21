import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";

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
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold">Settings</h1>
        <p className="text-sm text-muted-foreground">Manage your account.</p>
      </div>

      <div className="rounded-lg border border-border bg-card/40 p-5 space-y-4">
        <div className="space-y-1">
          <h2 className="font-medium">Change password</h2>
          <p className="text-xs text-muted-foreground">
            Signed in as {user?.email ?? "—"}. Choose a new password (at least 8
            characters).
          </p>
        </div>
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
            <div className="text-sm text-destructive" role="alert">
              {error}
            </div>
          ) : null}
          {done ? (
            <div className="text-sm text-primary" role="status">
              Password updated. Use it next time you sign in.
            </div>
          ) : null}
          <Button type="submit" loading={loading}>
            Update password
          </Button>
        </form>
      </div>
    </div>
  );
}
