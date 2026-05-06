export default {
  theme: {
    extend: {
      colors: {
        primary: "hsl(var(--primary))",
        "primary-foreground": "hsl(var(--primary-foreground))",
        destructive: "hsl(var(--destructive))",
        muted: "hsl(var(--muted))",
        "muted-foreground": "hsl(var(--muted-foreground))",
        border: "hsl(var(--border))"
      },
      spacing: {
        "2": "0.5rem",
        "4": "1rem"
      },
      borderRadius: {
        md: "0.375rem"
      }
    }
  },
  safelist: [
    "bg-primary",
    "text-primary-foreground",
    "bg-destructive",
    "text-muted-foreground",
    "rounded-md",
    "px-4",
    "py-2"
  ]
};
