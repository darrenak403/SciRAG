import { API_BASE, ApiError, errorFrom } from "@/lib/api-client";
import type { Paper } from "@/lib/types";

export const MAX_UPLOAD_MB = Number(process.env.NEXT_PUBLIC_MAX_UPLOAD_MB ?? 50);

/** Why a file cannot be uploaded, or null. Only what the browser can tell; the server checks again. */
export function refusal(file: File): string | null {
  const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (!isPdf) return "Only PDF files are currently supported.";
  if (file.size === 0) return "This file is empty.";
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    return `File exceeds the ${MAX_UPLOAD_MB} MB upload limit.`;
  }
  return null;
}

/**
 * Uploads one PDF. `onProgress` gets the fraction sent so far, as the browser reports it.
 * XMLHttpRequest because fetch cannot report how much of a request body has gone out.
 */
export function uploadPaper(
  file: File,
  onProgress: (fraction: number) => void,
  signal?: AbortSignal,
): Promise<Paper> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", `${API_BASE}/papers`);
    request.withCredentials = true;
    request.responseType = "json";
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(event.loaded / event.total);
    };
    request.onload = () => {
      if (request.status >= 200 && request.status < 300 && request.response) {
        resolve(request.response as Paper);
      } else if (request.status === 401) {
        window.location.assign("/login");
        reject(new ApiError(401, "Your session has ended. Sign in again."));
      } else {
        reject(errorFrom(request.status, request.response));
      }
    };
    request.onerror = () =>
      reject(new ApiError(0, "The upload was interrupted. Check your connection and try again.", "network"));
    request.onabort = () => reject(new DOMException("Upload cancelled", "AbortError"));
    signal?.addEventListener("abort", () => request.abort());

    const form = new FormData();
    form.append("file", file);
    request.send(form);
  });
}
