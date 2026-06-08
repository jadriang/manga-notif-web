import { getAuthToken } from "./auth-token";

const API_URL = import.meta.env.VITE_API_URL as string;

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = await getAuthToken();
  if (!token) throw new ApiError(401, "Not authenticated");

  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...options.headers,
    },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body.detail || `API error ${res.status}`);
  }
  return res.json();
}

export const api = {
  // Manga
  listManga: () => apiFetch<Manga[]>("/api/manga"),
  createManga: (url: string, title?: string) =>
    apiFetch<{ id: string; title: string; already_existed: boolean }>(
      "/api/manga",
      { method: "POST", body: JSON.stringify({ url, title }) }
    ),
  addMangaUrl: (mangaId: string, url: string) =>
    apiFetch<{ ok: boolean }>(`/api/manga/${mangaId}/add-url`, {
      method: "POST",
      body: JSON.stringify({ url }),
    }),

  // Subscriptions
  listSubscriptions: () =>
    apiFetch<{ manga_id: string; notify: boolean }[]>("/api/subscriptions"),
  toggleSubscription: (mangaId: string) =>
    apiFetch<{ subscribed: boolean }>("/api/subscriptions", {
      method: "POST",
      body: JSON.stringify({ manga_id: mangaId }),
    }),

  // Telegram
  generateTelegramLink: () =>
    apiFetch<{ token: string; telegram_chat_id: string | null }>(
      "/api/telegram/link",
      { method: "POST" }
    ),
  unlinkTelegram: () =>
    apiFetch<{ ok: boolean }>("/api/telegram/link", { method: "DELETE" }),

  // User
  getProfile: () => apiFetch<UserProfile>("/api/me"),

  // Invite redemption
  redeemInvite: (code: string) =>
    apiFetch<{ id: string; email: string; clerk_id: string }>(
      "/api/auth/redeem-invite",
      { method: "POST", body: JSON.stringify({ code }) }
    ),
};

export interface Manga {
  id: string;
  title: string;
  asura_slug: string | null;
  demonic_slug: string | null;
  cover_url: string | null;
  subscribed: boolean;
  latest_chapters: Record<string, string>;
}

export interface UserProfile {
  id: string;
  email: string;
  telegram_chat_id: string | null;
  created_at: string;
}
