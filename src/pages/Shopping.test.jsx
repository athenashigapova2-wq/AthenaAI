import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const { filter, createIdempotently, toast, t, authUser } = vi.hoisted(() => ({
  filter: vi.fn().mockResolvedValue([]),
  createIdempotently: vi.fn(),
  toast: vi.fn(),
  t: (key) => key,
  authUser: { id: "user-1" },
}));

vi.mock("@/lib/entities", () => ({
  entities: {
    ShoppingItem: {
      filter,
      createIdempotently,
      update: vi.fn(),
      delete: vi.fn(),
    },
  },
}));
vi.mock("@/lib/AuthContext", () => ({
  useAuth: () => ({ user: authUser }),
}));
vi.mock("@/components/ui/use-toast", () => ({ toast }));
vi.mock("@/lib/i18n", () => ({
  useLang: () => ({ t }),
}));

import Shopping from "@/pages/Shopping";

describe("Shopping save integrity", () => {
  it("allows retry and reuses the action idempotency key after an uncertain failure", async () => {
    createIdempotently
      .mockRejectedValueOnce(new Error("response lost"))
      .mockResolvedValueOnce({ id: "item-1", name: "Oats", checked: false });
    const user = userEvent.setup();
    render(<Shopping />);

    const input = await screen.findByPlaceholderText("shop_addPh");
    await user.type(input, "Oats");
    const add = screen.getByRole("button", { name: "shop_addPh" });

    await user.click(add);
    await waitFor(() => expect(toast).toHaveBeenCalled());
    expect(add).toBeEnabled();
    expect(input).toHaveValue("Oats");

    await user.click(add);
    await waitFor(() => expect(screen.getByText("Oats")).toBeInTheDocument());

    expect(createIdempotently).toHaveBeenCalledTimes(2);
    expect(createIdempotently.mock.calls[0][1]).toBe(createIdempotently.mock.calls[1][1]);
  });
});
