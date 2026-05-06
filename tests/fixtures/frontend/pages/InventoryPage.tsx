import { Button } from "@/components/ui/Button";
import { Card, DataTable, PageContainer, PageHeader, Toolbar } from "@/layouts";

export function InventoryPage() {
  return (
    <PageContainer>
      <PageHeader title="Inventory">
        <Button label="Create item" variant="primary" />
      </PageHeader>
      <Toolbar>
        <Button label="Delete selected" variant="danger" loading={false} />
      </Toolbar>
      <Card>
        <DataTable />
      </Card>
    </PageContainer>
  );
}
