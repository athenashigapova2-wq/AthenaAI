import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const { upsert, invalidateQueries, toast } = vi.hoisted(() => ({
  upsert: vi.fn(),
  invalidateQueries: vi.fn(),
  toast: vi.fn(),
}));

vi.mock("@/lib/entities", () => ({
  entities: { user_health_logs: { upsert } },
}));
vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries }),
}));
vi.mock("@/components/ui/use-toast", () => ({ toast }));
vi.mock("@/lib/i18n", () => ({
  useLang: () => ({ t: (key) => key }),
}));

import { HealthCheckIn } from "@/components/HealthCheckIn";

describe("HealthCheckIn save integrity", () => {
  it("re-enables saving after failure and retries the same daily upsert", async () => {
    upsert.mockRejectedValueOnce(new Error("network failure")).mockResolvedValueOnce({ id: "health-1" });
    const user = userEvent.setup();
    render(<HealthCheckIn />);

    const save = screen.getByRole("button", { name: "health_save" });
    await user.click(save);
    await waitFor(() => expect(toast).toHaveBeenCalled());
    expect(save).toBeEnabled();

    await user.click(save);
    await waitFor(() => expect(screen.getByRole("button", { name: "health_saved" })).toBeDisabled());

    expect(upsert).toHaveBeenCalledTimes(2);
    expect(upsert).toHaveBeenNthCalledWith(1, expect.objectContaining({ date: expect.any(String) }), "user_id,date");
    expect(upsert.mock.calls[0]).toEqual(upsert.mock.calls[1]);
  });
});
