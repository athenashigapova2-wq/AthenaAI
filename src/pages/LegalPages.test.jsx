import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import PrivacyPolicy from "./PrivacyPolicy";
import AccountDeletion from "./AccountDeletion";

describe("public legal pages", () => {
  it("publishes the privacy policy without authentication", () => {
    render(<MemoryRouter><PrivacyPolicy /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Privacy Policy" })).toBeInTheDocument();
    expect(screen.getByText(/GigaChat model provider/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "account deletion instructions" })).toHaveAttribute("href", "/account-deletion");
  });

  it("publishes actionable deletion instructions in both languages", () => {
    render(<MemoryRouter><AccountDeletion /></MemoryRouter>);
    expect(screen.getByRole("heading", { name: "Account deletion" })).toBeInTheDocument();
    expect(screen.getByText("DELETE")).toBeInTheDocument();
    expect(screen.getByText(/verify the account email and confirm/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Русский" }));
    expect(screen.getByRole("heading", { name: "Удаление аккаунта" })).toBeInTheDocument();
    expect(screen.getByText("DELETE")).toBeInTheDocument();
    expect(screen.getByText(/проверьте email аккаунта/)).toBeInTheDocument();
  });
});

