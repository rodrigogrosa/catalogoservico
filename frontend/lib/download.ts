"use client";

export async function downloadUrlToUser(url: string, filename: string): Promise<void> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error("download_failed");
  }

  const blob = await response.blob();
  await saveBlobToUser(blob, filename);
}

async function saveBlobToUser(blob: Blob, filename: string): Promise<void> {
  const picker = window.showSaveFilePicker;

  if (typeof picker === "function") {
    const extension = filename.includes(".") ? `.${filename.split(".").pop()}` : undefined;
    const handle = await picker({
      suggestedName: filename,
      types: extension
        ? [
            {
              description: "Arquivo do projeto",
              accept: {
                [blob.type || "application/octet-stream"]: [extension],
              },
            },
          ]
        : undefined,
    });
    const writable = await handle.createWritable();
    await writable.write(blob);
    await writable.close();
    return;
  }

  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

declare global {
  interface Window {
    showSaveFilePicker?: (options?: {
      suggestedName?: string;
      types?: Array<{
        description?: string;
        accept: Record<string, string[]>;
      }>;
    }) => Promise<{
      createWritable: () => Promise<{
        write: (data: Blob) => Promise<void>;
        close: () => Promise<void>;
      }>;
    }>;
  }
}
