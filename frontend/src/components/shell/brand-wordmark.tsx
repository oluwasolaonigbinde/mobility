import Image from "next/image";

export function BrandWordmark() {
  return (
    <span className="inline-flex items-center gap-3">
      <Image
        src="/brand/terrax/terrax-mark.jpg"
        width={773}
        height={618}
        alt="Terrax Media"
        className="h-8 w-10 object-contain"
        priority
      />
      <span className="font-display text-xl font-semibold tracking-tight">Cardvert</span>
    </span>
  );
}
