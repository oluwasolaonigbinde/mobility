import { VanPreview } from "@/components/brand/van-preview";

export function JobArtwork({
  assignmentId,
  kind,
  compact,
}: {
  assignmentId?: string;
  kind: "image" | "document" | null;
  compact: boolean;
}) {
  const source = assignmentId ? `/api/driver/jobs/${assignmentId}/artwork` : null;
  return (
    <div>
      <div className={`overflow-hidden ${compact ? "h-48" : "h-56"}`}>
        <VanPreview
          source={kind === "image" ? source : null}
          label={
            source && kind === "image"
              ? "Advert for this job on a car"
              : "Illustration of a car carrying an advert"
          }
        />
      </div>
      {source && kind !== "image" ? (
        <p className="text-muted px-4 pt-3 text-sm">Preview shows image files</p>
      ) : null}
      {source && kind === "document" ? (
        <a
          className="text-green inline-block p-3 text-sm underline"
          href={source}
          target="_blank"
          rel="noopener noreferrer"
        >
          Open this job’s advert
        </a>
      ) : null}
    </div>
  );
}
