interface RoleBadgeProps {
  label: string;
  tone: "green" | "coral";
}

export function RoleBadge({ label, tone }: RoleBadgeProps) {
  return <span className={`role-badge role-badge--${tone}`}>{label}</span>;
}
