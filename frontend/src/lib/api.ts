// Client API unique : toutes les requêtes du frontend passent par ici (règle n°1 de l'architecture).
// Le frontend ne parle qu'au backend /api/v1 : jamais au LLM ni à la base.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const SESSION_KEY = "smartcampus_session_id";
const TOKEN_KEY = "smartcampus_token";

export type ChatReply = { conversation_id: string; reply: string; language: string };
export type ChatMessage = { id?: string; role: "user" | "assistant"; content: string; language?: string | null };
export type Conversation = {
  id: string;
  title: string | null;
  detected_language: string | null;
  created_at: string;
  updated_at: string;
};
export type User = { id: string; email: string; full_name: string; role: string; created_at: string };

export class ApiError extends Error {
  constructor(message: string, public status: number, public code?: string) {
    super(message);
  }
}

type ErrorBody = {
  detail?: unknown;
  code?: string;
  errors?: { field?: string; message?: string }[];
};

const FIELD_LABELS: Record<string, string> = {
  email: "Email",
  password: "Mot de passe",
  full_name: "Nom complet",
  message: "Message",
};

/** Message lisible à partir du format d'erreur du backend {detail, code, errors} (y compris les 422). */
export function formatError(body: ErrorBody, status: number): string {
  if (status === 422 && Array.isArray(body.errors) && body.errors.length) {
    return body.errors
      .map((e) => {
        const field = e.field?.split(".").pop() ?? "champ";
        return `${FIELD_LABELS[field] ?? field} : ${e.message ?? "invalide"}`;
      })
      .join(" · ");
  }
  if (typeof body.detail === "string") return body.detail;
  if (Array.isArray(body.detail)) {
    // ancien format FastAPI : [{loc, msg}]
    return body.detail
      .map((d: { loc?: string[]; msg?: string }) => `${d.loc?.slice(-1)[0] ?? "champ"} : ${d.msg ?? "invalide"}`)
      .join(" · ");
  }
  if (status === 0) return "Serveur injoignable : vérifiez que le backend est démarré.";
  return `Erreur ${status}`;
}

// --- jeton JWT ---------------------------------------------------------------
export const auth = {
  getToken: () => (typeof window === "undefined" ? null : window.localStorage.getItem(TOKEN_KEY)),
  setToken: (t: string) => window.localStorage.setItem(TOKEN_KEY, t),
  clear: () => window.localStorage.removeItem(TOKEN_KEY),
};

async function request<T>(path: string, init: RequestInit = {}, withAuth = false): Promise<T> {
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  if (init.body && !(init.body instanceof URLSearchParams)) headers["Content-Type"] = "application/json";
  const token = auth.getToken();
  if (withAuth && token) headers["Authorization"] = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(formatError({}, 0), 0, "NETWORK_ERROR");
  }
  if (!res.ok) {
    const body: ErrorBody = await res.json().catch(() => ({}));
    if (res.status === 401 && (body.code === "INVALID_TOKEN" || body.code === "NOT_AUTHENTICATED")) auth.clear();
    throw new ApiError(formatError(body, res.status), res.status, body.code);
  }
  return res.json() as Promise<T>;
}

// --- session visiteur ----------------------------------------------------------
function storedSession(): string | null {
  return window.localStorage.getItem(SESSION_KEY);
}

export async function getSessionId(forceNew = false): Promise<string> {
  if (!forceNew) {
    const existing = storedSession();
    if (existing) return existing;
  }
  const { session_id } = await request<{ session_id: string }>("/sessions", { method: "POST" });
  window.localStorage.setItem(SESSION_KEY, session_id);
  return session_id;
}

/** Erreurs qui imposent une nouvelle session : expirée, ou rattachée à un compte dont on n'a pas le jeton. */
const SESSION_ERRORS = new Set(["SESSION_EXPIRED", "SESSION_ID_INVALID", "LOGIN_REQUIRED", "FORBIDDEN"]);

async function withSession<T>(call: (sessionId: string) => Promise<T>): Promise<T> {
  try {
    return await call(await getSessionId());
  } catch (e) {
    if (e instanceof ApiError && e.code && SESSION_ERRORS.has(e.code)) return call(await getSessionId(true));
    throw e;
  }
}

// --- chat ----------------------------------------------------------------------
/** Envoie un message : X-Session-Id toujours, JWT en plus si l'utilisateur est connecté. */
export async function sendMessage(message: string, conversationId?: string): Promise<ChatReply> {
  return withSession(async (sessionId) => {
    try {
      return await request<ChatReply>(
        "/chat/messages",
        {
          method: "POST",
          headers: { "X-Session-Id": sessionId },
          body: JSON.stringify({ message, conversation_id: conversationId ?? null }),
        },
        true,
      );
    } catch (e) {
      // conversation introuvable avec une nouvelle session : on repart sur une nouvelle conversation
      if (e instanceof ApiError && e.code === "CONVERSATION_NOT_FOUND" && conversationId) {
        return sendMessage(message);
      }
      throw e;
    }
  });
}

export const listConversations = () =>
  withSession((sessionId) =>
    request<Conversation[]>("/chat/conversations", { headers: { "X-Session-Id": sessionId } }, true),
  );

export const listMessages = (conversationId: string) =>
  withSession((sessionId) =>
    request<ChatMessage[]>(
      `/chat/conversations/${conversationId}/messages`,
      { headers: { "X-Session-Id": sessionId } },
      true,
    ),
  );

// --- authentification (SA-27) ---------------------------------------------------
export async function register(fullName: string, email: string, password: string): Promise<User> {
  // la session anonyme est transmise : l'historique du chat est rattaché au nouveau compte
  const sessionId = await getSessionId();
  return request<User>("/auth/register", {
    method: "POST",
    headers: { "X-Session-Id": sessionId },
    body: JSON.stringify({ full_name: fullName, email, password }),
  });
}

export async function login(email: string, password: string): Promise<void> {
  const { access_token } = await request<{ access_token: string }>("/auth/login", {
    method: "POST",
    body: new URLSearchParams({ username: email, password }),
  });
  auth.setToken(access_token);
}

export const me = () => request<User>("/auth/me", {}, true);

/** Déconnexion : on oublie le jeton ET la session (rattachée au compte) — un poste partagé ne garde rien. */
export function logout() {
  auth.clear();
  window.localStorage.removeItem(SESSION_KEY);
}
