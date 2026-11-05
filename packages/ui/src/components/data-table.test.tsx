import { fireEvent, render, screen, within } from "@testing-library/react";

import { type ColumnDef, DataTable } from "./data-table";
import { FormField } from "./form-field";
import { Input } from "./input";

type Row = { name: string; role: string };
const columns: ColumnDef<Row>[] = [
  { accessorKey: "name", header: "Name" },
  { accessorKey: "role", header: "Role", enableSorting: false },
];

describe("DataTable", () => {
  it("renders rows with an accessible caption", () => {
    render(
      <DataTable
        caption="Members"
        columns={columns}
        data={[
          { name: "Mia", role: "member" },
          { name: "Adam", role: "admin" },
        ]}
      />,
    );
    const table = screen.getByRole("table", { name: "Members" });
    expect(within(table).getAllByRole("row")).toHaveLength(3);
  });

  it("sorts by a sortable column and exposes aria-sort", () => {
    render(
      <DataTable
        caption="Members"
        columns={columns}
        data={[
          { name: "Mia", role: "member" },
          { name: "Adam", role: "admin" },
        ]}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /name/i }));
    const header = screen.getByRole("columnheader", { name: /name/i });
    expect(header).toHaveAttribute("aria-sort", "ascending");
    const cells = screen.getAllByRole("cell").map((c) => c.textContent);
    expect(cells[0]).toBe("Adam");
  });

  it("shows the empty state", () => {
    render(<DataTable caption="Members" columns={columns} data={[]} empty="No members" />);
    expect(screen.getByText("No members")).toBeInTheDocument();
  });
});

describe("FormField", () => {
  it("links hint and error to the control", () => {
    render(
      <FormField id="name" label="Name" hint="Shown to staff" error="Required">
        <Input id="name" />
      </FormField>,
    );
    const input = screen.getByLabelText("Name");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("Shown to staff Required");
    expect(screen.getByRole("alert")).toHaveTextContent("Required");
  });
});
