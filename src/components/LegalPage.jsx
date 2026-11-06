import React, { useState } from "react";
import { Link } from "react-router-dom";
import { ShieldCheck } from "lucide-react";

export default function LegalPage({ title, updatedAt, children }) {
  const [language, setLanguage] = useState(() => (
    typeof navigator !== "undefined" && navigator.language?.toLowerCase().startsWith("ru")
      ? "ru"
      : "en"
  ));

  return (
    <main className="min-h-screen bg-background px-4 py-8 sm:py-12">
      <article className="mx-auto max-w-3xl rounded-2xl border border-border bg-card p-6 shadow-sm sm:p-10">
        <header className="border-b border-border pb-6">
          <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
            <Link to="/" className="inline-flex items-center gap-2 font-heading text-xl text-foreground hover:text-primary">
              <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-primary-foreground">
                <ShieldCheck className="h-5 w-5" aria-hidden="true" />
              </span>
              Athena AI
            </Link>
            <div className="inline-flex rounded-lg border border-border p-1" aria-label="Document language">
              {[
                ["en", "English"],
                ["ru", "Русский"],
              ].map(([code, label]) => (
                <button
                  key={code}
                  type="button"
                  onClick={() => setLanguage(code)}
                  aria-pressed={language === code}
                  className={`rounded-md px-3 py-2 text-sm ${language === code ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <h1 className="font-heading text-3xl font-semibold text-foreground sm:text-4xl">
            {title[language]}
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {language === "ru" ? "Дата вступления в силу" : "Effective date"}: {updatedAt[language]}
          </p>
        </header>

        <div className="legal-copy py-7 text-foreground">
          {children(language)}
        </div>

        <footer className="flex flex-wrap gap-x-5 gap-y-3 border-t border-border pt-6 text-sm">
          <Link to="/privacy" className="text-primary hover:underline">Privacy Policy</Link>
          <Link to="/account-deletion" className="text-primary hover:underline">Account deletion</Link>
          <a href="https://aminashigapova.ru/" className="text-primary hover:underline" target="_blank" rel="noreferrer">
            Contact
          </a>
        </footer>
      </article>
    </main>
  );
}

