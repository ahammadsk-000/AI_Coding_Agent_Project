import { useEffect, type ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";

interface Props {
  children: ReactNode;
}

export function RequireAuth({ children }: Props) {
  const location = useLocation();
  const accessToken = useAuthStore((s) => s.accessToken);
  const user = useAuthStore((s) => s.user);
  const setUser = useAuthStore((s) => s.setUser);
  const setHydrated = useAuthStore((s) => s.setHydrated);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    enabled: Boolean(accessToken) && !user,
  });

  useEffect(() => {
    if (data) setUser(data);
  }, [data, setUser]);

  useEffect(() => {
    setHydrated(true);
  }, [setHydrated]);

  if (!accessToken) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  if (isLoading && !user) {
    return (
      <div className="flex min-h-screen items-center justify-center text-muted-foreground">
        Loading…
      </div>
    );
  }
  if (isError && !user) {
    return <Navigate to="/login" replace state={{ from: location }} />;
  }
  return <>{children}</>;
}
