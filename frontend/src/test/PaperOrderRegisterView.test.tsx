import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { paperOrderEvents } from "../fixtures/paperOrderEvents";
import { buildPaperOrderRegister, findPaperOrders } from "../lib/paperOrderRegister";
import { PaperOrderRegisterView } from "../views/PaperOrderRegisterView";

describe("registre PAPER local", () => {
  it.each([
    [1, "Ordre refusé", 2],
    [2, "Ordre annulé", 4],
    [3, "Position clôturée", 6],
    [4, "Position non résolue", 5],
  ])("retrouve TEST-ORD-%s et affiche uniquement les étapes enregistrées", (number, label, count) => {
    render(<PaperOrderRegisterView />);
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: `TEST-ORD-${number}` } });
    const heading = screen.getByText(`TEST-ORD-${number} · ${label}`);
    const fiche = heading.closest("details")!;
    fiche.open = true;
    expect(within(fiche).getAllByRole("listitem")).toHaveLength(count);
    expect(screen.getByRole("status")).toHaveTextContent("1 ordre");
  });

  it("rejoue la même chronologie et retrouve les identifiants liés", () => {
    const register = buildPaperOrderRegister(paperOrderEvents);
    expect(buildPaperOrderRegister([...paperOrderEvents].reverse())).toEqual(register);
    expect(findPaperOrders(register, "test-dec-1").map(order => order.id)).toEqual(["TEST-ORD-1"]);
    expect(findPaperOrders(register, "test-pos-4").map(order => order.id)).toEqual(["TEST-ORD-4"]);
    expect(findPaperOrders(register, "absent")).toEqual([]);
  });
});
