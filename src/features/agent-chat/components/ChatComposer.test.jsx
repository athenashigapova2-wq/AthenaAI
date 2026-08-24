import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import ChatComposer from "@/features/agent-chat/components/ChatComposer";

describe("ChatComposer", () => {
  it("prevents duplicate submissions while a message is in flight", async () => {
    const onSend = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(
      <ChatComposer input="hello" sending={false} error="" t={() => "Ask"} onChange={() => {}} onSend={onSend} />,
    );

    await user.click(screen.getByRole("button"));
    rerender(
      <ChatComposer input="hello" sending error="" t={() => "Ask"} onChange={() => {}} onSend={onSend} />,
    );
    await user.click(screen.getByRole("button"));

    expect(onSend).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("textbox")).toBeDisabled();
  });
});
