"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { ChatMessage, listMessages, sendMessage } from "@/lib/api";

const SUGGESTIONS = [
  "Quelle est la différence entre la Prépa et la Licence ?", // français
  "نحب نقرا informatique، شنوة تنصحني؟", // tunisien (lettres arabes)
  "chnowa el far9 bin prepa w licence ?", // Arabizi
];

const LANG_LABELS: Record<string, string> = { fr: "français", ar: "arabe", tn: "tunisien", arabizi: "Arabizi" };

const WELCOME: ChatMessage = {
  role: "assistant",
  content:
    "Ahla ! Je suis SmartCampus AI. Pose-moi tes questions sur les formations de l'IIT, de l'ISB et des écoles partenaires, en français, en tunisien ou en Arabizi.",
};

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<string>();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();
  const endRef = useRef<HTMLDivElement>(null);

  // reprise d'une conversation existante : /?c=<conversation_id> (lien depuis « Mon espace »)
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("c");
    if (!id) return;
    listMessages(id)
      .then((history) => {
        setConversationId(id);
        setMessages([WELCOME, ...history]);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    // accolades obligatoires : scrollIntoView renvoie une Promise dans les Chrome récents,
    // et un useEffect ne doit rien renvoyer d'autre qu'une fonction de nettoyage
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function submit(text: string) {
    const message = text.trim();
    if (!message || loading) return;
    setError(undefined);
    setInput("");
    setMessages((m) => [...m, { role: "user", content: message }]);
    setLoading(true);
    try {
      const res = await sendMessage(message, conversationId);
      setConversationId(res.conversation_id);
      setMessages((m) => [...m, { role: "assistant", content: res.reply, language: res.language }]);
      window.history.replaceState(null, "", `/?c=${res.conversation_id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit(input);
  };

  return (
    <main className="chat">
      <header>
        <h1>SmartCampus AI</h1>
        <p>Orientation IIT · ISB · ISA · 2I2S — sans création de compte</p>
      </header>

      <section className="messages" aria-live="polite">
        {messages.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`} dir="auto">
            {m.content}
            {m.role === "assistant" && m.language && (
              <span className="lang">langue détectée : {LANG_LABELS[m.language] ?? m.language}</span>
            )}
          </div>
        ))}
        {loading && <div className="bubble assistant typing">…</div>}
        <div ref={endRef} />
      </section>

      {messages.length === 1 && (
        <div className="suggestions">
          {SUGGESTIONS.map((s) => (
            <button key={s} onClick={() => submit(s)} dir="auto">
              {s}
            </button>
          ))}
        </div>
      )}

      {error && <p className="error">{error}</p>}

      <form onSubmit={onSubmit}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Écris ton message…"
          dir="auto"
          aria-label="Message"
        />
        <button type="submit" disabled={loading || !input.trim()}>
          Envoyer
        </button>
      </form>
    </main>
  );
}
