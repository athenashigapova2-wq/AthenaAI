import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

const loginViaEmailPassword = vi.fn();

vi.mock("@/lib/AuthContext", () => ({
  useAuth: () => ({ loginViaEmailPassword }),
}));

vi.mock("@/lib/i18n", () => ({
  LANGS: [{ code: "en", flag: "🇺🇸", label: "English" }],
  useLang: () => ({ lang: "en", setLang: vi.fn(), t: (key) => ({
    auth_welcome: "Welcome back",
    auth_loginSub: "Log in to your account",
    auth_noAccount: "Don't have an account?",
    auth_createOne: "Create one",
    auth_email: "Email",
    auth_password: "Password",
    auth_forgot: "Forgot password?",
    auth_login: "Log in",
    auth_loggingIn: "Logging in...",
    auth_invalid: "Invalid email or password",
  }[key] || key) }),
}));

import Login from "@/pages/Login";

describe("Login", () => {
  it("submits credentials and exposes authentication errors accessibly", async () => {
    loginViaEmailPassword.mockRejectedValueOnce(new Error("Invalid credentials"));
    const user = userEvent.setup();
    render(<MemoryRouter><Login /></MemoryRouter>);

    await user.type(screen.getByLabelText("Email"), "anna@example.test");
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    fireEvent.submit(screen.getByRole("button", { name: "Log in" }).closest("form"));

    expect(await screen.findByText("Invalid credentials")).toBeVisible();
    expect(loginViaEmailPassword).toHaveBeenCalledWith("anna@example.test", "wrong-password");
  });
});
