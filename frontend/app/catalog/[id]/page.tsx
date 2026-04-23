import { CatalogProductPageClient } from "@/components/catalog-product-page-client";

type Props = {
  params: Promise<{ id: string }>;
};

export default async function CatalogProductPage({ params }: Props) {
  const { id } = await params;
  return <CatalogProductPageClient id={id} />;
}
