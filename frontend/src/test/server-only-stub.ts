// Vitest alias target for the `server-only` package.
// In Next.js builds, importing `server-only` from client code is a hard error;
// unit tests run outside Next, so this stub makes the import inert there.
export {};
