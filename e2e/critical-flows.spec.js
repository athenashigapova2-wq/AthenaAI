import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { createMockState, installMockServices, login } from "./support/mockServices.js";

test("login → onboarding → chat", async ({ page }) => {
  const state = createMockState({ profile: null });
  await installMockServices(page, state);
  await login(page);

  await expect(page.getByRole("heading", { name: "What's your goal?" })).toBeVisible();
  await page.getByRole("button", { name: /Build muscle/ }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByText("Age", { exact: true }).locator("..").getByRole("spinbutton").fill("31");
  await page.getByText("Height (cm)").locator("..").getByRole("spinbutton").fill("168");
  await page.getByText("Weight (kg)").locator("..").getByRole("spinbutton").fill("64");
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Start tracking" }).click();

  await page.getByRole("link", { name: "Chat" }).click();
  await page.getByPlaceholder("Ask your coach…").fill("How are my macros?");
  await page.getByRole("button").filter({ has: page.locator("svg.lucide-send") }).click();
  await expect(page.getByText("Deterministic coach response")).toBeVisible();
});

test("meal logging persists a deterministic meal", async ({ page }) => {
  const state = createMockState();
  await installMockServices(page, state);
  await login(page);
  await page.getByRole("button", { name: "Log", exact: true }).click();
  await page.getByText("Name", { exact: true }).locator("..").getByRole("textbox").fill("Oatmeal");
  await page.getByText("Calories", { exact: true }).locator("..").getByRole("spinbutton").fill("420");
  await page.getByText("Protein (g)", { exact: true }).locator("..").getByRole("spinbutton").fill("22");
  await page.getByText("Carbs (g)", { exact: true }).locator("..").getByRole("spinbutton").fill("58");
  await page.getByText("Fat (g)", { exact: true }).locator("..").getByRole("spinbutton").fill("12");
  await page.getByRole("button", { name: "Log meal" }).click();
  await expect.poll(() => state.meals.length).toBe(1);
});

test("expired JWT is reported instead of starting a job", async ({ page }) => {
  const state = createMockState();
  await installMockServices(page, state);
  await login(page);
  await page.goto("/chat");
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await expect(page).toHaveURL(/\/login$/);
});

test("failed Redis/worker job is visible to the user", async ({ page }) => {
  const state = createMockState({ chatFailure: "Worker unavailable" });
  await installMockServices(page, state);
  await login(page);
  await page.goto("/chat");
  await page.getByPlaceholder("Ask your coach…").fill("hello");
  await page.getByPlaceholder("Ask your coach…").press("Enter");
  await expect(page.getByRole("alert")).toContainText("Worker unavailable");
});

test("duplicate submission creates exactly one job", async ({ page }) => {
  const state = createMockState({ chatDelayMs: 250 });
  await installMockServices(page, state);
  await login(page);
  await page.goto("/chat");
  const composer = page.getByPlaceholder("Ask your coach…");
  await composer.fill("only once");
  await composer.press("Enter");
  await composer.press("Enter");
  await expect.poll(() => state.chatPosts).toBe(1);
});

test("conversation switching loads the selected conversation", async ({ page }) => {
  const state = createMockState({
    conversations: [
      { id: "new", user_id: "user-e2e", title: "Newer conversation", updated_at: "2026-08-24T10:00:00Z" },
      { id: "old", user_id: "user-e2e", title: "Older conversation", updated_at: "2026-08-23T10:00:00Z" },
    ],
    messages: {
      new: [{ id: "m1", role: "assistant", content: "New message" }],
      old: [{ id: "m2", role: "assistant", content: "Old message" }],
    },
  });
  await installMockServices(page, state);
  await login(page);
  await page.goto("/chat");
  await expect(page.getByText("New message")).toBeVisible();
  await page.getByRole("button", { name: "Chat history" }).click();
  await page.getByText("Older conversation").click();
  await expect(page.getByText("Old message")).toBeVisible();
});

test("chat remains usable at a mobile viewport", async ({ page }) => {
  const state = createMockState();
  await installMockServices(page, state);
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await page.goto("/chat");
  await expect(page.getByPlaceholder("Ask your coach…")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("login and chat have no serious accessibility violations", async ({ page }) => {
  const state = createMockState();
  await installMockServices(page, state);
  await page.goto("/login");
  let results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.filter((item) => ["serious", "critical"].includes(item.impact))).toEqual([]);
  await login(page);
  await page.goto("/chat");
  results = await new AxeBuilder({ page }).analyze();
  expect(results.violations.filter((item) => ["serious", "critical"].includes(item.impact))).toEqual([]);
});

test.fixme("write tool confirmation blocks execution until explicit approval", async () => {
  // The current API executes write tools inside the Celery job before the client can approve them.
  // Keep this executable specification visible until a confirmation token/endpoint is introduced.
});
