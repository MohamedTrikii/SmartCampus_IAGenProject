"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";
import { login, register } from "@/lib/api";
import { notifyAuthChanged } from "@/lib/useCurrentUser";

export default function InscriptionPage() {
  const router = useRouter();
  const [form, setForm] = useState({ fullName: "", email: "", password: "", confirm: "" });
  const [error, setError] = useState<string>();
  const [loading, setLoading] = useState(false);

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [key]: e.target.value }));

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(undefined);
    if (form.password.length < 8) return setError("Le mot de passe doit contenir au moins 8 caractères.");
    if (form.password !== form.confirm) return setError("Les deux mots de passe ne correspondent pas.");
    setLoading(true);
    try {
      await register(form.fullName.trim(), form.email.trim(), form.password);
      await login(form.email.trim(), form.password);
      notifyAuthChanged();
      router.push("/mon-espace");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="auth-card">
      <h1>Créer un compte candidat</h1>
      <p className="muted">Votre conversation avec l&apos;assistant sera conservée dans votre espace.</p>
      <form onSubmit={onSubmit} className="stack">
        <label>
          Nom complet
          <input value={form.fullName} onChange={set("fullName")} required minLength={2} autoComplete="name" />
        </label>
        <label>
          Email
          <input type="email" value={form.email} onChange={set("email")} required autoComplete="email" />
        </label>
        <label>
          Mot de passe (8 caractères minimum)
          <input
            type="password"
            value={form.password}
            onChange={set("password")}
            required
            minLength={8}
            autoComplete="new-password"
          />
        </label>
        <label>
          Confirmer le mot de passe
          <input type="password" value={form.confirm} onChange={set("confirm")} required autoComplete="new-password" />
        </label>
        {error && <p className="error">{error}</p>}
        <button type="submit" className="btn" disabled={loading}>
          {loading ? "Création…" : "Créer mon compte"}
        </button>
      </form>
      <p className="muted">
        Déjà inscrit ? <Link href="/connexion">Se connecter</Link>
      </p>
    </main>
  );
}
