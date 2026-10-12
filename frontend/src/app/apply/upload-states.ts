"use client";

import { useCallback, useState } from "react";
import type { FilePickerState } from "@/components/ui/file-picker";

/**
 * Per-file upload state for the onboarding forms. It only reports progress: the forms keep
 * their own upload identity and retry rules, and `tracker` passes each upload result through
 * unchanged.
 */
export function useUploadStates<K extends string>(keys: readonly K[]) {
  const [idle] = useState(
    () => Object.fromEntries(keys.map((key) => [key, "idle"])) as Record<K, FilePickerState>,
  );
  const [states, setStates] = useState<Record<K, FilePickerState>>(idle);

  const set = useCallback(
    (key: K, state: FilePickerState) => setStates((current) => ({ ...current, [key]: state })),
    [],
  );
  const reset = useCallback(() => setStates(idle), [idle]);
  const clearUploading = useCallback(
    () =>
      setStates((current) => {
        const next = { ...current };
        for (const key of Object.keys(next) as K[]) {
          if (next[key] === "uploading") next[key] = "idle";
        }
        return next;
      }),
    [],
  );
  /** Wraps one upload so its picker shows uploading, then uploaded or failed. */
  const tracker = useCallback(
    (isCurrent: () => boolean) =>
      <T>(key: K, upload: Promise<T>): Promise<T> => {
        set(key, "uploading");
        return upload.then(
          (value) => {
            if (isCurrent()) set(key, "uploaded");
            return value;
          },
          (error: unknown) => {
            if (isCurrent()) set(key, "failed");
            throw error;
          },
        );
      },
    [set],
  );

  return { states, set, reset, clearUploading, tracker };
}
