import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import CalorieRing from "./CalorieRing";


describe("CalorieRing", () => {
  it("renders the rounded remaining calories and accessible labels", () => {
    const markup = renderToStaticMarkup(
      <CalorieRing
        remaining={419.6}
        target={2000}
        consumed={1580.4}
        label="remaining"
        ofLabel="of 2000 kcal"
      />,
    );

    expect(markup).toContain(">420</span>");
    expect(markup).toContain(">remaining</span>");
    expect(markup).toContain(">of 2000 kcal</span>");
  });

  it("caps the progress ring when consumption exceeds the target", () => {
    const markup = renderToStaticMarkup(
      <CalorieRing
        remaining={-100}
        target={2000}
        consumed={2100}
        label="remaining"
        ofLabel="of 2000 kcal"
      />,
    );

    expect(markup).toContain('stroke-dashoffset="0"');
  });
});
