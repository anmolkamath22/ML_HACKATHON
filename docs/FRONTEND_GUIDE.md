# Frontend guide

`src/pages/Workspace.tsx` coordinates modes, input IDs, results, health and errors. `ExcalidrawEditor` uses the official Excalidraw imperative API, rejects empty scenes, exports PNG via `exportToBlob` and scene data via `exportToJson`. `ImageUploader` checks MIME and file size before upload. Both call the typed API client. Artifact URLs from the API feed previews and download actions; local storage paths are never exposed.

Components are in `src/components`, contracts in `src/types.ts`, requests in `src/services/api.ts`, and responsive styling in `src/index.css`. Add a component by keeping request orchestration in Workspace and giving it typed props. `VITE_API_URL` configures the versioned API base. Install pins a semver range for Excalidraw; package lock records the resolved library API when npm install runs.
