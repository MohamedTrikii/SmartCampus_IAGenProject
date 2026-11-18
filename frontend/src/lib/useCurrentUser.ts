"use client";

import { useCallback, useEffect, useState } from "react";
import { auth, me, User } from "./api";

const EVENT = "smartcampus-auth-changed";

export function notifyAuthChanged() {
  window.dispatchEvent(new Event(EVENT));
}

export function useCurrentUser() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!auth.getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    try {
      setUser(await me());
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    window.addEventListener(EVENT, refresh);
    return () => window.removeEventListener(EVENT, refresh);
  }, [refresh]);

  return { user, loading, refresh };
}
