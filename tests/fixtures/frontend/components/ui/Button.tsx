import type { ReactNode } from "react";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";

export interface ButtonProps {
  label: string;
  variant?: "primary" | "secondary" | "ghost" | "danger";
  loading?: boolean;
  disabled?: boolean;
  children?: ReactNode;
}

/**
 * @ai.component ui.button
 * @ai.intent primary action, destructive action, form submit
 * @ai.avoid navigation link, row action menu
 * @ai.status stable
 * @ai.a11y icon-only usage requires aria-label
 */
export function Button(props: ButtonProps) {
  return <button className="bg-primary text-primary-foreground rounded-md px-4 py-2">{props.label}</button>;
}

export interface LegacyButtonProps {
  label: string;
}

/**
 * @ai.component ui.legacy-button
 * @ai.intent legacy action
 * @ai.avoid new UI, destructive action
 * @ai.status deprecated
 */
export function LegacyButton(props: LegacyButtonProps) {
  return <button className="bg-muted text-muted-foreground">{props.label}</button>;
}
