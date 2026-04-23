import { ProjectPageClient } from "@/components/project-page-client";

type Props = {
  params: Promise<{ id: string }>;
};

export default async function ProjectPage({ params }: Props) {
  const { id } = await params;
  return <ProjectPageClient id={id} />;
}
