import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const { createIdempotently, toast } = vi.hoisted(() => ({
  createIdempotently: vi.fn(),
  toast: vi.fn(),
}));

vi.mock("@/lib/entities", () => ({
  entities: { MealLog: { createIdempotently } },
}));
vi.mock("@/components/ui/use-toast", () => ({ toast }));
vi.mock("@/features/nutrition/api/nutritionApi", () => ({
  estimateMeal: vi.fn(),
}));
vi.mock("@/lib/i18n", () => ({
  useLang: () => ({ t: (key) => key, lang: "ru" }),
}));

import LogMealDialog from "@/components/LogMealDialog";

describe("LogMealDialog save integrity", () => {
  it("re-enables retry and reuses the same idempotency key after failure", async () => {
    const savedMeal = { id: "meal-1", name: "Oats" };
    createIdempotently
      .mockRejectedValueOnce(new Error("temporary network failure"))
      .mockResolvedValueOnce(savedMeal);
    const onLogged = vi.fn();
    const user = userEvent.setup();
    render(
      <LogMealDialog open onOpenChange={() => {}} onLogged={onLogged} />,
    );

    await user.type(screen.getByPlaceholderText("log_namePh"), "Oats");
    const numberInputs = document.querySelectorAll('input[type="number"]');
    ["350", "15", "55", "8"].forEach((value, index) => {
      fireEvent.change(numberInputs[index], { target: { value } });
    });

    const saveButton = screen.getByRole("button", { name: "log_logMeal" });
    await user.click(saveButton);
    await waitFor(() => expect(toast).toHaveBeenCalled());
    expect(saveButton).toBeEnabled();
    expect(screen.getByPlaceholderText("log_namePh")).toHaveValue("Oats");

    await user.click(saveButton);
    await waitFor(() => expect(onLogged).toHaveBeenCalledWith(savedMeal));

    expect(createIdempotently).toHaveBeenCalledTimes(2);
    expect(createIdempotently.mock.calls[0][1]).toBe(createIdempotently.mock.calls[1][1]);
  });
});
