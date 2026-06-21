import { useState, type FormEvent, type ReactNode } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import {
  Sparkles,
  Mail,
  Lock,
  Eye,
  EyeOff,
  ArrowRight,
  GitBranch,
  Search,
  MessageSquare,
  ShieldCheck,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation() as { state?: { from?: { pathname: string } } };
  const setTokens = useAuthStore((s) => s.setTokens);
  const setUser = useAuthStore((s) => s.setUser);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await api.login(email, password);
      setTokens({
        accessToken: res.tokens.access_token,
        refreshToken: res.tokens.refresh_token,
        accessExpiresAt: res.tokens.access_token_expires_at,
        refreshExpiresAt: res.tokens.refresh_token_expires_at,
      });
      setUser(res.user);
      navigate(location.state?.from?.pathname ?? "/dashboard", { replace: true });
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Unexpected error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="relative min-h-screen overflow-hidden bg-background">
      {/* decorative background: glow orbs + faint grid */}
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -left-40 -top-40 h-[28rem] w-[28rem] rounded-full bg-sky-500/20 blur-3xl" />
        <div className="absolute -right-40 top-1/3 h-[32rem] w-[32rem] rounded-full bg-indigo-500/20 blur-3xl" />
        <div className="absolute -bottom-40 left-1/4 h-[26rem] w-[26rem] rounded-full bg-violet-500/10 blur-3xl" />
        <div
          className="absolute inset-0 opacity-[0.035]"
          style={{
            backgroundImage:
              "linear-gradient(hsl(var(--foreground)) 1px, transparent 1px), linear-gradient(90deg, hsl(var(--foreground)) 1px, transparent 1px)",
            backgroundSize: "44px 44px",
          }}
        />
      </div>

      <div className="relative grid min-h-screen lg:grid-cols-2">
        {/* ---- brand / marketing panel ---- */}
        <div className="hidden flex-col justify-between p-12 lg:flex">
          <div className="flex items-center gap-2 text-lg font-semibold">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-sky-400 to-indigo-500 shadow-lg shadow-sky-500/30">
              <Sparkles className="h-5 w-5 text-white" />
            </div>
            <span>AI Coding Agent</span>
          </div>

          <div className="max-w-md space-y-6">
            <h1 className="text-4xl font-bold leading-tight tracking-tight">
              Chat, search, and ship across your{" "}
              <span className="bg-gradient-to-r from-sky-400 to-indigo-400 bg-clip-text text-transparent">
                codebase
              </span>
              .
            </h1>
            <p className="text-muted-foreground">
              Point the agent at your repositories and get answers grounded in
              your real code — powered by hybrid search and your choice of LLM.
            </p>
            <ul className="space-y-3 text-sm">
              <Feature
                icon={<GitBranch className="h-4 w-4" />}
                text="Ingest any git repo — parsed, chunked, embedded"
              />
              <Feature
                icon={<Search className="h-4 w-4" />}
                text="Hybrid semantic + keyword code search"
              />
              <Feature
                icon={<MessageSquare className="h-4 w-4" />}
                text="RAG chat with streaming answers and citations"
              />
              <Feature
                icon={<ShieldCheck className="h-4 w-4" />}
                text="JWT auth, rate limits, and audit logging"
              />
            </ul>
          </div>

          <p className="text-xs text-muted-foreground">
            Open &amp; self-hostable — bring your own LLM.
          </p>
        </div>

        {/* ---- sign-in panel ---- */}
        <div className="flex items-center justify-center p-6">
          <div className="w-full max-w-sm">
            {/* compact brand for small screens */}
            <div className="mb-8 flex items-center justify-center gap-2 text-lg font-semibold lg:hidden">
              <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-sky-400 to-indigo-500">
                <Sparkles className="h-5 w-5 text-white" />
              </div>
              <span>AI Coding Agent</span>
            </div>

            <div className="rounded-2xl border border-border bg-card/60 p-8 shadow-2xl backdrop-blur-xl">
              <div className="mb-6 space-y-1 text-center">
                <h2 className="text-2xl font-semibold tracking-tight">Welcome back</h2>
                <p className="text-sm text-muted-foreground">Sign in to your account</p>
              </div>

              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-1.5">
                  <label htmlFor="email" className="text-xs font-medium text-muted-foreground">
                    Email
                  </label>
                  <div className="relative">
                    <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      id="email"
                      type="email"
                      placeholder="you@example.com"
                      className="pl-10"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      autoComplete="email"
                    />
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label htmlFor="password" className="text-xs font-medium text-muted-foreground">
                    Password
                  </label>
                  <div className="relative">
                    <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                    <Input
                      id="password"
                      type={showPassword ? "text" : "password"}
                      placeholder="••••••••"
                      className="pl-10 pr-10"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                      autoComplete="current-password"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((v) => !v)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground transition-colors hover:text-foreground"
                      aria-label={showPassword ? "Hide password" : "Show password"}
                      tabIndex={-1}
                    >
                      {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                    </button>
                  </div>
                </div>

                {error ? (
                  <div
                    className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive"
                    role="alert"
                  >
                    {error}
                  </div>
                ) : null}

                <Button
                  type="submit"
                  loading={loading}
                  className="group w-full bg-gradient-to-r from-sky-500 to-indigo-500 shadow-lg shadow-sky-500/25 transition-all hover:shadow-sky-500/40"
                >
                  Sign in
                  <ArrowRight className="ml-1.5 h-4 w-4 transition-transform group-hover:translate-x-0.5" />
                </Button>
              </form>

              <div className="mt-6 text-center text-sm text-muted-foreground">
                No account?{" "}
                <Link to="/register" className="font-medium text-primary hover:underline">
                  Create one
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function Feature({ icon, text }: { icon: ReactNode; text: string }) {
  return (
    <li className="flex items-center gap-3">
      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg border border-border bg-card/60 text-primary">
        {icon}
      </span>
      <span className="text-muted-foreground">{text}</span>
    </li>
  );
}
