"use client";

import { useCallback, useEffect, useRef } from "react";
import type { DocumentUploadProgress } from "./onboarding-upload";

type Entry = {
  file: File;
  context: string;
  requestId: string;
  progress: DocumentUploadProgress;
  running?: Promise<string>;
  fileId?: string;
};

/** Each mounted form owns its private progress; no browser storage is involved. */
export function useDocumentUploads() {
  const entries = useRef(new Map<string, Entry>());
  const active = useRef(true);
  const epoch = useRef(0);

  const remove = useCallback((key: string) => {
    const entry = entries.current.get(key);
    if (entry) entry.progress.cancelled = true;
    entries.current.delete(key);
  }, []);
  const clear = useCallback(() => {
    for (const key of entries.current.keys()) remove(key);
    epoch.current += 1;
  }, [remove]);
  useEffect(() => {
    active.current = true;
    const logout = () => {
      active.current = false;
      clear();
    };
    window.addEventListener("cardvert-driver-logout", logout);
    return () => {
      active.current = false;
      clear();
      window.removeEventListener("cardvert-driver-logout", logout);
    };
  }, [clear]);

  function fence() {
    const selectedEpoch = epoch.current;
    return () => active.current && selectedEpoch === epoch.current;
  }

  function upload(
    key: string,
    file: File,
    context: string,
    send: (requestId: string, progress: DocumentUploadProgress) => Promise<string>,
  ): Promise<string> {
    if (!active.current) return Promise.reject(new Error("Please sign in again."));
    let entry = entries.current.get(key);
    if (entry && (entry.file !== file || entry.context !== context)) {
      remove(key);
      entry = undefined;
    }
    if (!entry) {
      entry = { file, context, requestId: crypto.randomUUID(), progress: {} };
      entries.current.set(key, entry);
    }
    if (entry.fileId) return Promise.resolve(entry.fileId);
    if (entry.running) return entry.running;
    const selected = entry;
    const running = send(selected.requestId, selected.progress).then((id) => {
      if (active.current && entries.current.get(key) === selected) selected.fileId = id;
      return id;
    });
    selected.running = running;
    void running
      .finally(() => {
        selected.running = undefined;
      })
      .catch(() => {});
    return running;
  }
  return { upload, remove, clear, fence, alive: () => active.current };
}
