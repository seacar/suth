"use client";

import { useEffect, useState } from "react";
import { useApi } from "@/lib/api-context";
import { PageHeader } from "@/components/PageHeader";
import type { PersonaRecord } from "@/lib/types";

export default function PersonasPage() {
  const api = useApi();
  const [personas, setPersonas] = useState<PersonaRecord[]>([]);

  const [id, setId] = useState("");
  const [name, setName] = useState("");
  const [digitalLiteracy, setDigitalLiteracy] = useState("medium");
  const [device, setDevice] = useState("mobile");
  const [interactionMode, setInteractionMode] = useState("pointer");
  const [forbiddenAssumptionsText, setForbiddenAssumptionsText] = useState("");
  const [noDomChangeThreshold, setNoDomChangeThreshold] = useState(2);
  const [repeatedLoopThreshold, setRepeatedLoopThreshold] = useState(3);
  const [frustrationThreshold, setFrustrationThreshold] = useState(8);
  const [status, setStatus] = useState<string | null>(null);

  function loadPersonas() {
    api
      .request<PersonaRecord[]>("/personas")
      .then(setPersonas)
      .catch(() => {});
  }

  useEffect(loadPersonas, [api]);

  async function save() {
    const definition = {
      id,
      name,
      digital_literacy: digitalLiteracy,
      device,
      interaction_mode: interactionMode,
      forbidden_assumptions: forbiddenAssumptionsText.split("\n").map((s) => s.trim()).filter(Boolean),
      abandonment_rules: [
        { trigger: "no_dom_change_after_click", threshold: noDomChangeThreshold },
        { trigger: "repeated_step_loop", threshold: repeatedLoopThreshold },
        { trigger: "frustration_score_exceeds", threshold: frustrationThreshold },
      ],
      objective_template: "{{objective}}",
    };

    try {
      await api.request("/personas", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(definition),
      });
      setStatus("saved");
      loadPersonas();
    } catch (err) {
      setStatus(`error: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Library"
        title="Personas"
        description="Create a new persona or browse the versions already synced into Postgres."
      />

      <div className="split">
        <section className="panel">
          <div className="panel-head">
            <h2>New persona</h2>
          </div>
          <div className="panel-body stack">
            <div className="row stretch">
              <div className="field">
                <label htmlFor="persona-id">ID</label>
                <input id="persona-id" value={id} onChange={(e) => setId(e.target.value)} placeholder="my-persona-v1" />
              </div>
              <div className="field">
                <label htmlFor="persona-name">Display name</label>
                <input id="persona-name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Impatient shopper" />
              </div>
            </div>

            <div className="row stretch">
              <div className="field">
                <label htmlFor="persona-literacy">Digital literacy</label>
                <select id="persona-literacy" value={digitalLiteracy} onChange={(e) => setDigitalLiteracy(e.target.value)}>
                  <option value="low">low</option>
                  <option value="medium">medium</option>
                  <option value="high">high</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="persona-device">Device</label>
                <select id="persona-device" value={device} onChange={(e) => setDevice(e.target.value)}>
                  <option value="mobile">mobile</option>
                  <option value="desktop">desktop</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="persona-mode">Interaction</label>
                <select id="persona-mode" value={interactionMode} onChange={(e) => setInteractionMode(e.target.value)}>
                  <option value="pointer">pointer</option>
                  <option value="keyboard">keyboard</option>
                </select>
              </div>
            </div>

            <div className="field">
              <label htmlFor="persona-assumptions">Forbidden assumptions</label>
              <textarea
                id="persona-assumptions"
                rows={3}
                value={forbiddenAssumptionsText}
                onChange={(e) => setForbiddenAssumptionsText(e.target.value)}
                placeholder="One assumption per line"
              />
            </div>

            <div className="row stretch">
              <div className="field">
                <label htmlFor="persona-nodom">No-DOM-change clicks</label>
                <input
                  id="persona-nodom"
                  type="number"
                  min={1}
                  max={10}
                  value={noDomChangeThreshold}
                  onChange={(e) => setNoDomChangeThreshold(Number(e.target.value))}
                />
              </div>
              <div className="field">
                <label htmlFor="persona-loop">Repeated-action loop</label>
                <input
                  id="persona-loop"
                  type="number"
                  min={1}
                  max={10}
                  value={repeatedLoopThreshold}
                  onChange={(e) => setRepeatedLoopThreshold(Number(e.target.value))}
                />
              </div>
              <div className="field">
                <label htmlFor="persona-frustration">Frustration ceiling</label>
                <input
                  id="persona-frustration"
                  type="number"
                  min={1}
                  max={20}
                  value={frustrationThreshold}
                  onChange={(e) => setFrustrationThreshold(Number(e.target.value))}
                />
              </div>
            </div>

            <div className="row">
              <button type="button" className="primary" disabled={!id} onClick={save}>
                Save persona
              </button>
              {status && (
                <span className={status.startsWith("saved") ? "ok-text" : "error-text"} style={{ margin: 0 }}>
                  {status}
                </span>
              )}
            </div>
          </div>
        </section>

        <section className="panel">
          <div className="panel-head">
            <h2>Existing personas</h2>
            <span className="muted">{personas.length}</span>
          </div>
          <div className="panel-body" style={{ paddingTop: "0.5rem" }}>
            {personas.length === 0 ? (
              <div className="empty">
                <strong>Library is empty</strong>
                Sync YAML personas or save one from this form.
              </div>
            ) : (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>ID</th>
                      <th>Name</th>
                      <th>Version</th>
                    </tr>
                  </thead>
                  <tbody>
                    {personas.map((p) => (
                      <tr key={p.id}>
                        <td className="mono">{p.id}</td>
                        <td>{p.name ?? "—"}</td>
                        <td className="mono">{p.version}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>
      </div>
    </>
  );
}
