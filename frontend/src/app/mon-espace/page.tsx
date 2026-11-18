"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Conversation, listConversations } from "@/lib/api";
import { useCurrentUser } from "@/lib/useCurrentUser";

const ROLE_LABELS: Record<string, string> = {
  candidate: "Candidat",
  academic_iit: "Responsable académique IIT",
  academic_isb: "Responsable académique ISB",
  interviewer: "Responsable entretien",
  direction: "Direction",
  admin: "Administrateur",
};

export default function MonEspacePage() {
  const { user, loading } = useCurrentUser();
  const router = useRouter();
  const [conversations, setConversations] = useState<Conversation[] | null>(null);
  const [error, setError] = useState<string>();

  useEffect(() => {
    if (!loading && !user) router.replace("/connexion");
  }, [loading, user, router]);

  useEffect(() => {
    if (!user) return;
    listConversations()
      .then(setConversations)
      .catch((e: Error) => setError(e.message));
  }, [user]);

  if (loading || !user) return <main className="auth-card">Chargement…</main>;

  return (
    <main className="auth-card wide">
      <h1>Bonjour {user.full_name}</h1>
      <dl className="profile">
        <dt>Email</dt>
        <dd>{user.email}</dd>
        <dt>Rôle</dt>
        <dd>{ROLE_LABELS[user.role] ?? user.role}</dd>
        <dt>Membre depuis</dt>
        <dd>{new Date(user.created_at).toLocaleDateString("fr-FR")}</dd>
      </dl>

      <h2>Mes conversations</h2>
      {error && <p className="error">{error}</p>}
      {conversations === null && !error && <p className="muted">Chargement…</p>}
      {conversations?.length === 0 && <p className="muted">Aucune conversation pour l&apos;instant.</p>}
      {conversations && conversations.length > 0 && (
        <ul className="conversations">
          {conversations.map((c) => (
            <li key={c.id}>
              <Link href={`/?c=${c.id}`} dir="auto">
                {c.title ?? "Conversation"}
              </Link>
              <span className="muted"> · {new Date(c.updated_at).toLocaleString("fr-FR")}</span>
            </li>
          ))}
        </ul>
      )}

      <p className="muted">
        Le suivi de votre préinscription, vos QCM et vos rendez-vous apparaîtront ici dans les prochaines versions.
      </p>
      <Link href="/" className="btn">
        Nouvelle conversation
      </Link>
    </main>
  );
}
