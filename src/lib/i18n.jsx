import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import englishMessages from "@/locales/en.json";

export const LANGS = [
  { code: "en", flag: "🇺🇸", label: "English" },
  { code: "ru", flag: "🇷🇺", label: "Русский" },
  { code: "fr", flag: "🇫🇷", label: "Français" },
  { code: "es", flag: "🇪🇸", label: "Español" },
  { code: "zh", flag: "🇨🇳", label: "中文" },
];

export const CURRENCY = { en: "$", ru: "₽", fr: "€", es: "€", zh: "¥" };
export const LANG_NAME = { en: "English", ru: "Russian", fr: "French", es: "Spanish", zh: "Chinese" };
export const CURRENCY_RATE = { rub: 1, usd: 1 / 78.03, eur: 1 / 88.89, cny: 1 / 11.5 };
export const LANG_CURRENCY_CODE = { en: "usd", ru: "rub", fr: "eur", es: "eur", zh: "cny" };

const localeLoaders = {
  en: async () => englishMessages,
  ru: () => import("@/locales/ru.json").then((module) => module.default),
  fr: () => import("@/locales/fr.json").then((module) => module.default),
  es: () => import("@/locales/es.json").then((module) => module.default),
  zh: () => import("@/locales/zh.json").then((module) => module.default),
};

const localeCache = new Map([["en", englishMessages]]);
const normalizeLanguage = (language) => Object.hasOwn(localeLoaders, language) ? language : "en";

export async function loadLocale(language) {
  const normalized = normalizeLanguage(language);
  if (!localeCache.has(normalized)) {
    localeCache.set(normalized, await localeLoaders[normalized]());
  }
  return localeCache.get(normalized);
}

const LangContext = createContext({
  lang: "en",
  setLang: () => {},
  localeLoading: false,
  t: (key) => key,
});

export function LangProvider({ children }) {
  const [lang, setLang] = useState(() => normalizeLanguage(localStorage.getItem("lang") || "en"));
  const [messages, setMessages] = useState(() => localeCache.get(lang) || englishMessages);
  const [localeLoading, setLocaleLoading] = useState(!localeCache.has(lang));

  useEffect(() => {
    let active = true;
    const normalized = normalizeLanguage(lang);
    localStorage.setItem("lang", normalized);
    document.documentElement.lang = normalized;
    setMessages(localeCache.get(normalized) || englishMessages);
    setLocaleLoading(!localeCache.has(normalized));

    loadLocale(normalized)
      .then((loadedMessages) => {
        if (active) setMessages(loadedMessages);
      })
      .catch(() => {
        if (active) {
          setMessages(englishMessages);
          setLang("en");
        }
      })
      .finally(() => {
        if (active) setLocaleLoading(false);
      });

    return () => {
      active = false;
    };
  }, [lang]);

  const t = useCallback((key, params = {}) => {
    let value = messages[key] ?? englishMessages[key] ?? key;
    for (const [name, replacement] of Object.entries(params)) {
      value = value.split(`{${name}}`).join(String(replacement));
    }
    return value;
  }, [messages]);

  const contextValue = useMemo(
    () => ({ lang, setLang, localeLoading, t }),
    [lang, localeLoading, t],
  );

  return <LangContext.Provider value={contextValue}>{children}</LangContext.Provider>;
}

export const useLang = () => useContext(LangContext);
