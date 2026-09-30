// Save a file the API answers (audit export, incident bundle) under the server's file name.
// The token goes in a header, so a plain link cannot do it; resolves with an error message,
// or null on success.
export async function download(
  path: string,
  token: string | null,
  fallbackName: string,
): Promise<string | null> {
  const response = await fetch(`/api/v1${path}`, {
    headers: { Authorization: `Bearer ${token ?? ''}` },
    cache: 'no-store',
  });
  if (!response.ok) return `The export failed (HTTP ${String(response.status)}).`;
  const name =
    /filename="([^"]+)"/.exec(response.headers.get('Content-Disposition') ?? '')?.[1] ??
    fallbackName;
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.click();
  URL.revokeObjectURL(url);
  return null;
}
