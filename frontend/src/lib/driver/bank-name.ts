/** Display names from the supported bank directory in app/adapters/banks.py. */
const names: Readonly<Record<string, string>> = {
  "999992": "OPay",
  "50515": "Moniepoint",
  "999991": "PalmPay",
  "50211": "Kuda Bank",
  "058": "GTBank",
  "044": "Access Bank",
  "011": "First Bank of Nigeria",
  "033": "UBA",
  "057": "Zenith Bank",
  "023": "Citibank Nigeria",
  "050": "Ecobank Nigeria",
  "070": "Fidelity Bank",
  "214": "First City Monument Bank",
  "00103": "Globus Bank",
  "301": "Jaiz Bank",
  "082": "Keystone Bank",
  "076": "Polaris Bank",
  "105": "PremiumTrust Bank",
  "101": "Providus Bank",
  "221": "Stanbic IBTC Bank",
  "068": "Standard Chartered Bank",
  "232": "Sterling Bank",
  "100": "Suntrust Bank",
  "102": "Titan Bank",
  "032": "Union Bank",
  "215": "Unity Bank",
  "035": "Wema Bank",
};

export function bankDisplayName(code: string): string {
  return names[code] ?? `Bank code ${code}`;
}
