import { describe, expect, it } from "vitest";

import en from "@/locales/en.json";
import es from "@/locales/es.json";
import fr from "@/locales/fr.json";
import ru from "@/locales/ru.json";
import zh from "@/locales/zh.json";

const cycleKeys = Object.keys(en).filter((key) => key.startsWith("cycle_"));
const locales = { en, es, fr, ru, zh };

describe("cycle tracker translations", () => {
  it.each(Object.entries(locales))("provides every cycle key for %s", (_language, messages) => {
    expect(cycleKeys.length).toBeGreaterThan(0);
    for (const key of cycleKeys) {
      expect(messages[key], key).toEqual(expect.any(String));
      expect(messages[key].trim(), key).not.toBe("");
    }
  });
});
