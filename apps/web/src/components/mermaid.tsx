import { useEffect, useRef, useState } from "react";

/**
 * Renders a Mermaid diagram. Mermaid is dynamically imported so it stays out of
 * the main bundle (only loaded when a diagram is actually shown). If the diagram
 * source is invalid, falls back to showing the raw text.
 */
export function Mermaid({ code }: { code: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setError(false);
    (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({ startOnLoad: false, theme: "dark", securityLevel: "loose" });
        // Validate first (suppressErrors avoids Mermaid injecting a stray error
        // graphic into the DOM); fall back to raw text if invalid.
        const valid = await mermaid.parse(code, { suppressErrors: true });
        if (!valid) {
          if (!cancelled) setError(true);
          return;
        }
        const id = "m" + Math.random().toString(36).slice(2);
        const { svg } = await mermaid.render(id, code);
        if (!cancelled && ref.current) ref.current.innerHTML = svg;
      } catch {
        if (!cancelled) setError(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [code]);

  if (error) {
    return (
      <pre className="overflow-auto rounded-md border border-border bg-muted/30 p-3 text-xs text-muted-foreground">
        {code}
      </pre>
    );
  }
  return <div ref={ref} className="overflow-auto [&_svg]:mx-auto [&_svg]:max-w-full" />;
}
