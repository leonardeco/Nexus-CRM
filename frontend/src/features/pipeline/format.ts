const COP = new Intl.NumberFormat("es-CO", {
  style: "currency",
  currency: "COP",
  maximumFractionDigits: 0,
});

export function formatCOP(value: string | number | null | undefined): string {
  const amount = typeof value === "number" ? value : Number(value ?? 0);
  return COP.format(Number.isFinite(amount) ? amount : 0);
}
