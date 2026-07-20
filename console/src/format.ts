export function formatEpoch(value?: number): string {
  if (!value) return "-";
  const milliseconds = value < 1_000_000_000_000 ? value * 1000 : value;
  return new Date(milliseconds).toLocaleString();
}
