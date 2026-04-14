export interface ChatResponse {
  text: string;
  diagram: string | null;
}

export interface UploadResponse {
  text: string;
  diagram: string | null;
}

export async function uploadFiles(files: File[]): Promise<UploadResponse> {
  const form = new FormData();
  for (const f of files) form.append("files", f);
  const res = await fetch("/upload", { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Upload failed: ${res.status}`);
  }
  return res.json();
}

export async function sendMessage(message: string): Promise<ChatResponse> {
  const res = await fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Chat failed: ${res.status}`);
  }
  return res.json();
}

export async function resetSession(): Promise<void> {
  await fetch("/reset", { method: "POST" });
}
