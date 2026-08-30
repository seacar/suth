"use client";

import { FolderOpen } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useApi } from "@/lib/api-context";
import { browseProjects } from "@/lib/projects-api";
import type { BrowseResponse } from "@/lib/types";

interface FolderBrowserProps {
  path: string;
  onPathChange: (path: string) => void;
}

declare global {
  interface Window {
    showDirectoryPicker?: (options?: { mode?: "read" | "readwrite" }) => Promise<{ name: string }>;
  }
}

export function FolderBrowser({ path, onPathChange }: FolderBrowserProps) {
  const api = useApi();
  const [browse, setBrowse] = useState<BrowseResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draftPath, setDraftPath] = useState(path);
  const [pickedName, setPickedName] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setDraftPath(path);
    setPickedName(null);
  }, [path]);

  useEffect(() => {
    let cancelled = false;
    setError(null);
    browseProjects(api, path)
      .then((result) => {
        if (!cancelled) setBrowse(result);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      });
    return () => {
      cancelled = true;
    };
  }, [api, path]);

  function commitPath(next: string) {
    const trimmed = next.trim();
    if (trimmed && trimmed !== path) {
      onPathChange(trimmed);
    }
  }

  function applyPickedFolderName(name: string) {
    setDraftPath(name);
    setPickedName(name);
  }

  async function pickFolder() {
    if (window.showDirectoryPicker) {
      try {
        const handle = await window.showDirectoryPicker({ mode: "read" });
        applyPickedFolderName(handle.name);
      } catch (err) {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setError(err instanceof Error ? err.message : String(err));
      }
      return;
    }
    fileInputRef.current?.click();
  }

  function handleFileInputChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const relPath = (file as File & { webkitRelativePath?: string }).webkitRelativePath;
    applyPickedFolderName(relPath ? relPath.split("/")[0] : file.name);
  }

  return (
    <div className="folder-browser">
      <div className="folder-browser-toolbar">
        <button type="button" className="ghost folder-browser-choose" onClick={pickFolder}>
          <FolderOpen size={16} aria-hidden />
          Choose folder…
        </button>
        <input
          className="folder-browser-path-input"
          value={draftPath}
          onChange={(e) => {
            setDraftPath(e.target.value);
            setPickedName(null);
          }}
          onBlur={() => commitPath(draftPath)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              commitPath(draftPath);
            }
          }}
          aria-label="Folder path"
          spellCheck={false}
          placeholder="./my-app or /absolute/path"
        />
        <input
          ref={fileInputRef}
          type="file"
          // @ts-expect-error non-standard attributes that trigger the native folder picker
          webkitdirectory=""
          directory=""
          multiple
          hidden
          onChange={handleFileInputChange}
        />
      </div>

      <div className="folder-browser-meta">
        <div className="folder-browser-meta-copy">
          {error ? (
            <p className="error-text folder-browser-hint">{error}</p>
          ) : pickedName ? (
            <p className="folder-browser-hint">
              Picked <span className="mono">{pickedName}</span> — browsers hide the full path, so confirm or
              finish typing above, then press Enter.
            </p>
          ) : (
            <p className="folder-browser-hint muted">
              Resolves to <span className="mono">{browse?.abs_path ?? "…"}</span>
            </p>
          )}
        </div>
        {browse?.config_exists ? <span className="badge ok">suth_config.json</span> : null}
      </div>
    </div>
  );
}
