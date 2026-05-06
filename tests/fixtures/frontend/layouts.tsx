import { ReactNode } from "react";

export function PageContainer({ children }: { children: ReactNode }) {
  return <main>{children}</main>;
}

export function PageHeader({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <header>
      <h1>{title}</h1>
      {children}
    </header>
  );
}

export function Toolbar({ children }: { children: ReactNode }) {
  return <div>{children}</div>;
}

export function Card({ children }: { children: ReactNode }) {
  return <section>{children}</section>;
}

export function DataTable() {
  return <table />;
}

export function FormSection({ children }: { children: ReactNode }) {
  return <section>{children}</section>;
}

export function EmptyState() {
  return <div />;
}
