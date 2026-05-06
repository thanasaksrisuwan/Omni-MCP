import { Button } from "@/components/ui/WrongButton";
import { LegacyButton } from "@/components/ui/Button";
import { IconGhost } from "@/icons";

export function UnsafeUsage({ color }: { color: string }) {
  return (
    <div className={`bg-${color}-500`}>
      <Button variant="red" className="bg-neon" />
      <UnknownCard title="No manifest evidence" />
      <IconGhost />
      <LegacyButton label="Old action" />
    </div>
  );
}
