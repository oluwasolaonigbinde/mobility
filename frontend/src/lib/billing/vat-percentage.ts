export const VAT_PERCENTAGE_ERROR = "Enter VAT from 0 to 100%, with up to 4 decimal places.";

function units(value: string, places: number, maximum: bigint): bigint | null {
  const text = value.trim();
  if (!new RegExp(`^\\d+(?:\\.\\d{1,${places}})?$`).test(text)) return null;
  const [whole = "0", fraction = ""] = text.split(".");
  const result =
    BigInt(whole) * BigInt(10) ** BigInt(places) + BigInt(fraction.padEnd(places, "0"));
  return result <= maximum ? result : null;
}

function decimal(value: bigint, places: number): string {
  const digits = value.toString().padStart(places + 1, "0");
  const fraction = digits.slice(-places).replace(/0+$/, "");
  return digits.slice(0, -places) + (fraction ? `.${fraction}` : "");
}

export function vatPercentageToRate(value: string): string | null {
  const parsed = units(value, 4, BigInt(1000000));
  return parsed === null ? null : decimal(parsed, 6);
}

export function vatRateToPercentage(value: string): string | null {
  const parsed = units(value, 6, BigInt(1000000));
  return parsed === null ? null : decimal(parsed, 4);
}

export function smallVatConfirmation(value: string): string | null {
  const parsed = units(value, 4, BigInt(1000000));
  if (parsed === null || parsed === BigInt(0) || parsed >= BigInt(10000)) return null;
  const percentage = decimal(parsed, 4);
  return `VAT is ${percentage}%. Did you mean ${decimal(parsed * BigInt(100), 4)}%? Save using ${percentage}%?`;
}
