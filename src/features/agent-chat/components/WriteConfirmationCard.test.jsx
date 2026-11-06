import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import WriteConfirmationCard from "./WriteConfirmationCard";

const translations = {
  chat_writeConfirmTitle: "Подтвердите запись",
  chat_writeConfirmBody: "Проверьте параметры.",
  chat_writeConfirm: "Подтвердить",
  chat_writeReject: "Отменить",
  chat_writeAction_log_meal: "Запись приёма пищи",
  chat_writeFieldName: "Приём пищи",
  chat_writeFieldMealType: "Тип приёма пищи",
  chat_writeFieldCalories: "Калории",
  chat_writeFieldProtein: "Белки",
};

describe("WriteConfirmationCard", () => {
  it("renders a human-readable preview instead of raw JSON", () => {
    const { container } = render(
      <WriteConfirmationCard
        action={{
          tool_name: "log_meal",
          preview: {
            name: "Куриная грудка и гречка",
            meal_type: "lunch",
            calories: 458,
            protein_g: 52,
          },
        }}
        busy={false}
        error=""
        t={(key) => translations[key] || key}
        onConfirm={vi.fn()}
        onReject={vi.fn()}
      />,
    );

    expect(screen.getByText("Запись приёма пищи")).toBeInTheDocument();
    expect(screen.getByText("Куриная грудка и гречка")).toBeInTheDocument();
    expect(screen.getByText("458 kcal")).toBeInTheDocument();
    expect(screen.getByText("52 g")).toBeInTheDocument();
    expect(container.querySelector("pre")).not.toBeInTheDocument();
    expect(container).not.toHaveTextContent('"calories"');
  });
});
