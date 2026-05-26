// Server Component wrapper — its only job is to unwrap the async `params`
// promise (a Next.js 16 breaking change) and hand the id to the client child
// that actually does the data fetching with TanStack Query.
//
// Splitting like this keeps the client bundle minimal and matches the
// recommended pattern in the Next.js 16 upgrade guide.

import { EventDetailClient } from "./client";

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <EventDetailClient id={id} />;
}
