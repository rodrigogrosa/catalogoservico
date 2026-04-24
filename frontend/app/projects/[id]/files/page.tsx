import { ProjectPageSectionClient } from "@/components/project-page-client";

type Props = {
  params: Promise<{ id: string }>;
};

export default async function ProjectFilesPage({ params }: Props) {
  const { id } = await params;
  return <ProjectPageSectionClient id={id} section="files" />;
}
