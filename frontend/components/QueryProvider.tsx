"use client";

// TanStack Query provider — wraps the app so any client component can use
// useQuery / useMutation hooks. Marked "use client" because QueryClient
// itself isn't serializable across the server/client boundary.

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { useState, type ReactNode } from "react";

export function QueryProvider({ children }: { children: ReactNode }) {
  // useState ensures the client is created once per browser tab — not on every
  // render. Creating a new QueryClient per render would discard all caches.
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Match the backend's cadence: events refetch becomes useful every
            // few minutes, not every second. 30s feels live-enough without
            // hammering the API on tab focus.
            staleTime: 30_000,
            retry: 1,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={client}>
      {children}
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}
