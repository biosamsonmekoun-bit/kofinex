import { redirect } from "next/navigation";

export default async function OrganizationIndex({ params }: { params: Promise<{ orgId: string }> }) {
  const { orgId } = await params;
  redirect(`/organizations/${orgId}/companies`);
}
