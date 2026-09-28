/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Absolute backend API base, e.g. http://127.0.0.1:8010/api.
   *  Leave unset in dev so requests go through the Vite proxy at /api. */
  readonly VITE_API_BASE?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
