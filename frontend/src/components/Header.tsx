"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { logout } from "@/lib/api";
import { notifyAuthChanged, useCurrentUser } from "@/lib/useCurrentUser";

export default function Header() {
  const { user, loading } = useCurrentUser();
  const router = useRouter();

  const onLogout = () => {
    logout();
    notifyAuthChanged();
    router.push("/");
  };

  return (
    <nav className="topbar">
      <Link href="/" className="brand">
        SmartCampus AI
      </Link>
      <div className="nav-actions">
        {loading ? null : user ? (
          <>
            <Link href="/mon-espace">{user.full_name}</Link>
            <button className="link" onClick={onLogout}>
              Déconnexion
            </button>
          </>
        ) : (
          <>
            <Link href="/connexion">Se connecter</Link>
            <Link href="/inscription" className="btn">
              Créer un compte
            </Link>
          </>
        )}
      </div>
    </nav>
  );
}
