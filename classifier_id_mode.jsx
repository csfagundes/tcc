import { useState, useRef, useCallback } from "react";
import * as XLSX from "xlsx";

// Photo URL is already in the file as player_photo_url column.
// We just classify each unique player_id once, then join back to all rows.

const DELAY_MS = 900;
const sleep = ms => new Promise(r => setTimeout(r, ms));

const CLS_CLR  = { Branco: "#c8b090", Pardo: "#a07840", Preto: "#9070c8" };
const CONF_CLR = { alta: "#4ade80", media: "#facc15", baixa: "#f87171" };
const ST = {
  pending:     { border: "#1e2a3a", color: "#2a4060", label: "pending"      },
  classifying: { border: "#1a5a4a", color: "#4ab090", label: "classifying…" },
  done:        { border: "#1a5a2a", color: "#4ab060", label: "done ✓"       },
  error:       { border: "#5a1a1a", color: "#c04040", label: "error"        },
};

// ── Claude Vision ──────────────────────────────────────────────────────────
async function classifyPhoto(playerName, imageUrl) {
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "claude-sonnet-4-20250514",
      max_tokens: 300,
      system: `You are a research assistant for an academic study on racial bias in Brazilian football officiating (Série A 2018–2023), using the heteroidentification methodology from Silva, Bastos & Silva (Revista Movimento, 2025).

Classify the person's phenotypical skin color using 3 simplified IBGE categories:
• Branco — light skin, predominantly European features
• Pardo  — intermediate/brown skin, mixed features
• Preto  — dark skin, predominantly Afro-descendant features

Reply ONLY with valid JSON. No prose, no markdown, no code fences.
Schema: {"classificacao":"Branco","confianca":"alta","justificativa":"one sentence"}
confianca: alta | media | baixa`,
      messages: [{
        role: "user",
        content: [
          { type: "image", source: { type: "url", url: imageUrl } },
          { type: "text",  text: `Classify athlete "${playerName}" — IBGE skin-color category for racial bias research. JSON only.` }
        ]
      }]
    })
  });
  const d = await res.json();
  if (d.error) throw new Error(d.error.message);
  const raw = d.content?.find(b => b.type === "text")?.text ?? "{}";
  return JSON.parse(raw.replace(/```json|```/g, "").trim());
}

// ── File parser ────────────────────────────────────────────────────────────
function parseFile(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = e => {
      try {
        const wb   = XLSX.read(new Uint8Array(e.target.result), { type: "array" });
        const ws   = wb.Sheets[wb.SheetNames[0]];
        const rows = XLSX.utils.sheet_to_json(ws, { header: 1, defval: "" });
        const hdr  = rows[0].map(h => String(h).toLowerCase().trim());

        const idIdx    = hdr.findIndex(h => h === "player_id");
        const nameIdx  = hdr.findIndex(h => ["player_name","player","nome","atleta","jogador","name"].includes(h));
        const photoIdx = hdr.findIndex(h => h === "player_photo_url");
        const posIdx   = hdr.findIndex(h => h === "position");

        if (idIdx === -1)    throw new Error("Column 'player_id' not found. Run the SofaScore extractor first.");
        if (photoIdx === -1) throw new Error("Column 'player_photo_url' not found.");

        // Build unique player map keyed by player_id
        const playerMap = {};
        rows.slice(1).forEach(row => {
          const pid = String(row[idIdx] ?? "").trim();
          if (!pid || playerMap[pid]) return;
          playerMap[pid] = {
            player_id:        pid,
            player_name:      String(row[nameIdx  >= 0 ? nameIdx  : 0] ?? "").trim(),
            position:         String(row[posIdx   >= 0 ? posIdx   : 0] ?? "").trim(),
            player_photo_url: String(row[photoIdx] ?? "").trim(),
            status: "pending",
            data: null,
            error: null,
          };
        });

        resolve({ header: rows[0], allRows: rows, idIdx, playerMap });
      } catch (err) { reject(err); }
    };
    reader.onerror = reject;
    reader.readAsArrayBuffer(file);
  });
}

// ── Export: join classification back to every original row ─────────────────
function exportEnriched(parsed, playerMap) {
  const extra = ["classificacao", "confianca", "justificativa"];
  const hdr   = [...parsed.header, ...extra];

  const rows = parsed.allRows.slice(1).map(row => {
    const pid = String(row[parsed.idIdx] ?? "").trim();
    const p   = playerMap[pid];
    const ext = p?.data
      ? extra.map(k => p.data[k] ?? "")
      : [p?.error ?? "error", "", ""];
    return [...row, ...ext];
  });

  const ws = XLSX.utils.aoa_to_sheet([hdr, ...rows]);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "Cartoes_Classificados");
  XLSX.writeFile(wb, "cartoes_com_raca.xlsx");
}

// ── App ────────────────────────────────────────────────────────────────────
export default function App() {
  const [parsed,    setParsed]    = useState(null);
  const [players,   setPlayers]   = useState({});   // pid → player obj
  const [running,   setRunning]   = useState(false);
  const [fileError, setFileError] = useState("");
  const stopRef = useRef(false);

  const pids = Object.keys(players);

  const stats = {
    total:  pids.length,
    done:   pids.filter(k => players[k].status === "done").length,
    errors: pids.filter(k => players[k].status === "error").length,
    Branco: pids.filter(k => players[k].data?.classificacao === "Branco").length,
    Pardo:  pids.filter(k => players[k].data?.classificacao === "Pardo").length,
    Preto:  pids.filter(k => players[k].data?.classificacao === "Preto").length,
  };

  const handleFile = async f => {
    setFileError(""); setParsed(null); setPlayers({});
    try {
      const p = await parseFile(f);
      setParsed(p);
      setPlayers({ ...p.playerMap });
    } catch (e) { setFileError(e.message); }
  };

  const update = useCallback((pid, patch) => {
    setPlayers(prev => ({ ...prev, [pid]: { ...prev[pid], ...patch } }));
  }, []);

  const run = useCallback(async () => {
    if (!parsed) return;
    stopRef.current = false;
    setRunning(true);

    const pending = pids.filter(k => players[k].status !== "done");
    for (const pid of pending) {
      if (stopRef.current) break;
      const p = players[pid];
      if (!p.player_photo_url) { update(pid, { status: "error", error: "No photo URL" }); continue; }

      update(pid, { status: "classifying" });
      try {
        const data = await classifyPhoto(p.player_name, p.player_photo_url);
        update(pid, { status: "done", data });
      } catch (e) {
        update(pid, { status: "error", error: e.message });
      }
      await sleep(DELAY_MS);
    }
    setRunning(false);
  }, [parsed, pids, players, update]);

  const pct = stats.total > 0 ? (stats.done / stats.total) * 100 : 0;
  const totalRows = parsed ? parsed.allRows.length - 1 : 0;

  return (
    <div style={{
      minHeight: "100vh", background: "#07090f", color: "#bcc4cc",
      fontFamily: "'Courier New', monospace", fontSize: 12,
    }}>
      {/* HEADER */}
      <div style={{ padding: "20px 28px 16px", borderBottom: "1px solid #0e141e",
        background: "linear-gradient(180deg,#0b1020 0%,#07090f 100%)",
        display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 20 }}>
        <div>
          <div style={{ fontSize: 9, letterSpacing: "0.25em", color: "#1e3a50", marginBottom: 5 }}>
            RACIAL BIAS · BRASILEIRÃO SÉRIE A 2018–2023 · UFABC
          </div>
          <h1 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: "#7ab0d8" }}>
            Race Classifier — SofaScore ID Mode
          </h1>
          <p style={{ margin: "4px 0 0", fontSize: 10, color: "#1e3a50", lineHeight: 1.7 }}>
            Upload <code style={{ color: "#3a6a88" }}>cartoes_brasileirao_2018_2023.csv</code> or <code style={{ color: "#3a6a88" }}>jogadores_unicos_com_foto.csv</code><br/>
            Player photo URLs are read directly from <code style={{ color: "#3a6a88" }}>player_photo_url</code> column — zero search calls needed.
          </p>
        </div>
        {stats.total > 0 && (
          <div style={{ display: "flex", gap: 18, flexShrink: 0 }}>
            {[
              ["card rows",      totalRows,      "#2a4a6a"],
              ["unique players", stats.total,    "#3a6a9a"],
              ["classified",     stats.done,     "#5090c0"],
              ["Branco",         stats.Branco,   CLS_CLR.Branco],
              ["Pardo",          stats.Pardo,    CLS_CLR.Pardo ],
              ["Preto",          stats.Preto,    CLS_CLR.Preto ],
            ].map(([label, val, color]) => (
              <div key={label} style={{ textAlign: "center" }}>
                <div style={{ fontSize: 20, fontWeight: 700, color, lineHeight: 1 }}>{val}</div>
                <div style={{ fontSize: 9, color: "#1e3050", letterSpacing: "0.08em", marginTop: 3 }}>
                  {String(label).toUpperCase()}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "270px 1fr", gap: 20, padding: "20px 28px", alignItems: "start" }}>

        {/* SIDEBAR */}
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>

          {/* Upload */}
          <div onClick={() => document.getElementById("fi").click()}
            style={{ border: `1px dashed ${parsed ? "#2a5070" : "#142030"}`,
              borderRadius: 8, padding: "22px 16px", textAlign: "center",
              cursor: "pointer", background: parsed ? "#08121c" : "#07090f" }}>
            <input id="fi" type="file" accept=".csv,.xlsx,.xls"
              style={{ display: "none" }}
              onChange={e => e.target.files[0] && handleFile(e.target.files[0])} />
            <div style={{ fontSize: 26, marginBottom: 8 }}>{parsed ? "📊" : "📂"}</div>
            {parsed
              ? <><div style={{ color: "#5090b8", fontWeight: 700, fontSize: 11 }}>File loaded</div>
                  <div style={{ color: "#1e3a50", fontSize: 10, marginTop: 3 }}>
                    {totalRows} card rows · {stats.total} unique players
                  </div></>
              : <><div style={{ color: "#1e3a50" }}>Drop CSV / XLSX here</div>
                  <div style={{ color: "#0e1e2a", fontSize: 10, marginTop: 3 }}>or click to browse</div></>}
          </div>
          {fileError && (
            <div style={{ background: "#150808", border: "1px solid #4a1a1a",
              color: "#c06060", borderRadius: 6, padding: "8px 10px", fontSize: 10 }}>
              ⚠ {fileError}
            </div>
          )}

          {/* Flow diagram */}
          <div style={{ background: "#080e16", border: "1px solid #0e1e2e", borderRadius: 8, padding: "12px" }}>
            <div style={{ fontSize: 9, color: "#1e3a50", letterSpacing: "0.15em", marginBottom: 10 }}>PIPELINE</div>
            {[
              ["player_id",        "native SofaScore ID",    "#3a6a88"],
              ["player_photo_url", "built into CSV already", "#3a8a68"],
              ["Claude Vision",    "IBGE classification",    "#6a5a88"],
              ["Export XLSX",      "all card rows enriched", "#3a6a48"],
            ].map(([title, sub, col]) => (
              <div key={title} style={{ display: "flex", gap: 10, marginBottom: 8, alignItems: "flex-start" }}>
                <div style={{ width: 3, alignSelf: "stretch", background: col, borderRadius: 2, flexShrink: 0 }} />
                <div>
                  <div style={{ color: col, fontSize: 10, fontWeight: 700 }}>{title}</div>
                  <div style={{ color: "#1e3a50", fontSize: 9 }}>{sub}</div>
                </div>
              </div>
            ))}
            <div style={{ marginTop: 10, padding: "8px 10px", background: "#0a1820",
              borderRadius: 6, border: "1px solid #0e2030" }}>
              <div style={{ color: "#1e5a38", fontSize: 9 }}>
                ✓ <strong style={{ color: "#2a7a50" }}>Zero search calls</strong><br/>
                Player IDs already in file → photo URL constructed directly → classify only
              </div>
            </div>
          </div>

          {/* Progress */}
          {stats.total > 0 && (
            <div style={{ background: "#080e16", border: "1px solid #0e1e2e", borderRadius: 8, padding: "12px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                <span style={{ fontSize: 9, color: "#1e3a50", letterSpacing: "0.12em" }}>PROGRESS</span>
                <span style={{ color: "#3a6a90", fontSize: 10 }}>{stats.done}/{stats.total}</span>
              </div>
              <div style={{ height: 5, background: "#0a1018", borderRadius: 3, overflow: "hidden", marginBottom: 10 }}>
                <div style={{ width: `${pct}%`, height: "100%",
                  background: "linear-gradient(90deg,#1a5080,#40a0d8)",
                  transition: "width .4s ease", borderRadius: 3 }} />
              </div>
              {["Branco","Pardo","Preto"].map(cls => {
                const c = stats[cls], p = stats.done > 0 ? c / stats.done * 100 : 0;
                return (
                  <div key={cls} style={{ marginBottom: 7 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 2 }}>
                      <span style={{ color: "#2a4a60", fontSize: 10 }}>{cls}</span>
                      <span style={{ color: CLS_CLR[cls], fontSize: 10, fontWeight: 700 }}>
                        {c} <span style={{ color: "#1e3050", fontWeight: 400 }}>({p.toFixed(0)}%)</span>
                      </span>
                    </div>
                    <div style={{ height: 3, background: "#0a1018", borderRadius: 2 }}>
                      <div style={{ width: `${p}%`, height: "100%", background: CLS_CLR[cls], borderRadius: 2, transition: "width .5s" }} />
                    </div>
                  </div>
                );
              })}
              {stats.errors > 0 && <div style={{ color: "#6a2a2a", fontSize: 9, marginTop: 6 }}>
                ⚠ {stats.errors} error{stats.errors > 1 ? "s" : ""} — will retry on resume
              </div>}
            </div>
          )}

          {/* Controls */}
          {stats.total > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <button onClick={running ? () => { stopRef.current = true; } : run}
                style={{ background: running ? "#120818" : "#0a1e30",
                  border: `1px solid ${running ? "#4a1a6a" : "#1a4a70"}`,
                  color: running ? "#b060e0" : "#50a0d8",
                  borderRadius: 6, padding: "10px", fontSize: 12, fontWeight: 700,
                  cursor: "pointer", fontFamily: "inherit", letterSpacing: "0.05em" }}>
                {running
                  ? "⏹  STOP"
                  : stats.done > 0
                    ? `▶  RESUME  (${stats.total - stats.done} left)`
                    : `▶  CLASSIFY  ${stats.total} players`}
              </button>
              <button onClick={() => exportEnriched(parsed, players)}
                disabled={stats.done === 0}
                style={{ background: stats.done > 0 ? "#081812" : "#07090f",
                  border: `1px solid ${stats.done > 0 ? "#1a5030" : "#0e1820"}`,
                  color: stats.done > 0 ? "#3aaa60" : "#142030",
                  borderRadius: 6, padding: "9px", fontSize: 11,
                  cursor: stats.done > 0 ? "pointer" : "default",
                  fontFamily: "inherit", letterSpacing: "0.05em" }}>
                ↓  EXPORT ENRICHED XLSX ({stats.done} / {stats.total})
              </button>
            </div>
          )}
        </div>

        {/* TABLE */}
        <div style={{ overflowX: "auto" }}>
          {pids.length === 0 ? (
            <div style={{ textAlign: "center", padding: "80px 0", color: "#0e1e2e" }}>
              <div style={{ fontSize: 52, marginBottom: 14 }}>⚽</div>
              <div style={{ fontSize: 13 }}>Upload your SofaScore card events file to begin.</div>
              <div style={{ fontSize: 10, marginTop: 8, color: "#0a1820", lineHeight: 1.8 }}>
                Required columns:<br/>
                <span style={{ color: "#1e3a50" }}>player_id · player_name · player_photo_url</span><br/>
                <span style={{ color: "#0a1420" }}>Generated by extrair_cartoes_sofascore.py</span>
              </div>
            </div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid #0e141e" }}>
                  {["#","ID","Player","Pos","Photo","Classification","Confidence","Justification","Status"].map(h => (
                    <th key={h} style={{ textAlign: "left", padding: "7px 10px", fontSize: 8,
                      color: "#1a3050", letterSpacing: "0.18em", textTransform: "uppercase",
                      fontWeight: 700, whiteSpace: "nowrap" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {pids.map((pid, i) => {
                  const p   = players[pid];
                  const st  = ST[p.status] ?? ST.pending;
                  const act = p.status === "classifying";
                  return (
                    <tr key={pid} style={{ borderBottom: "1px solid #08101a",
                      background: act ? "#090f18" : i % 2 === 0 ? "#07090f" : "#080c12",
                      transition: "background .3s" }}>
                      <td style={{ padding: "9px 10px", color: "#1a2a3a", fontSize: 10 }}>{i+1}</td>
                      <td style={{ padding: "9px 10px", color: "#2a4a60", fontSize: 10, fontFamily: "monospace" }}>{pid}</td>
                      <td style={{ padding: "9px 10px", color: "#7a9ab8", fontWeight: 700, whiteSpace: "nowrap" }}>{p.player_name}</td>
                      <td style={{ padding: "9px 10px", color: "#2a4050", fontSize: 10 }}>{p.position || "—"}</td>
                      <td style={{ padding: "9px 10px" }}>
                        {p.player_photo_url
                          ? <img src={p.player_photo_url} alt={p.player_name}
                              onError={e => { e.target.style.display = "none"; }}
                              style={{ width: 30, height: 36, objectFit: "cover", borderRadius: 3, border: "1px solid #1a2a3a" }} />
                          : <span style={{ color: "#0e1e2e" }}>—</span>}
                      </td>
                      <td style={{ padding: "9px 10px" }}>
                        {p.data?.classificacao
                          ? <span style={{ background: "#0a0f18",
                              border: `1px solid ${CLS_CLR[p.data.classificacao]}`,
                              color: CLS_CLR[p.data.classificacao],
                              borderRadius: 4, padding: "2px 8px", fontSize: 10, fontWeight: 700 }}>
                              {p.data.classificacao}
                            </span>
                          : <span style={{ color: "#0e1e2e" }}>—</span>}
                      </td>
                      <td style={{ padding: "9px 10px" }}>
                        {p.data?.confianca
                          ? <span style={{ color: CONF_CLR[p.data.confianca], fontSize: 10, fontWeight: 700 }}>
                              {p.data.confianca}
                            </span>
                          : <span style={{ color: "#0e1e2e" }}>—</span>}
                      </td>
                      <td style={{ padding: "9px 10px", color: "#2a4050", fontSize: 10, maxWidth: 220, lineHeight: 1.4 }}>
                        {p.data?.justificativa
                          ?? (p.error ? <span style={{ color: "#6a2020" }}>{p.error}</span> : "—")}
                      </td>
                      <td style={{ padding: "9px 10px", whiteSpace: "nowrap" }}>
                        <span style={{ background: "#07090f", border: `1px solid ${st.border}`,
                          color: st.color, borderRadius: 4, padding: "2px 7px", fontSize: 9,
                          letterSpacing: "0.05em", display: "inline-flex", alignItems: "center", gap: 4 }}>
                          {act && <span style={{ animation: "spin 1s linear infinite", display: "inline-block" }}>⟳</span>}
                          {st.label}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
