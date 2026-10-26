(() => {
const { Masthead, Dropzone, Button, Progress, Alert, ReportSection, FindingRow, Karyogram, KaryogramLegend, DataTable, StateMark, SearchInput, Term, Icon } = window.LucidaseDesignSystem_241006;
function allRows(D) { return D.records.concat(D.negative, D.gaps, D.insufficient); }
function lociOf(rows) { const seen = {}; return rows.map(r => { const m = window.LDS_META[r.gene]; const off = seen[r.gene] ? 9 : 0; seen[r.gene] = 1; return { id: r.id, label: m.topic, chrom: m.chrom, pos: m.pos + (off ? 3 : 0), offset: off, state: r.state }; }); }
function Intro({ phase, pct, run }) {
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 48, alignItems: "flex-start" }}>
      <div style={{ flex: "1 1 420px", display: "flex", flexDirection: "column", gap: 20, maxWidth: 560 }}>
        <Masthead basePath="../../assets/logo/" title="Read your raw DNA file, on your own device" />
        <p style={{ margin: 0, font: "400 18px/1.6 var(--font-serif)", color: "var(--text-muted)", textWrap: "pretty" }}>Lucidase checks 14 well-studied places in 12 genes and explains each result in plain words — including what it could not test.</p>
        <Dropzone disabled={phase === "loading"} onFile={run} description="Works with files from 23andMe, AncestryDNA and MyHeritage, and VCF files. Your file is read on this device and never uploaded.">
          <Button icon="folder-open" disabled={phase === "loading"}>Choose your DNA file</Button>
          <Button variant="secondary" disabled={phase === "loading"} onClick={run}>Try a made-up example file</Button>
        </Dropzone>
        {phase === "loading" && <Progress value={pct} label={pct < 35 ? "Reading sample-23andme.txt" : pct < 80 ? "Comparing your file with the 14 checks" : "Writing your results"} />}
      </div>
      <div style={{ flex: "1 1 320px", display: "flex", flexDirection: "column", gap: 28, paddingTop: 8 }}>
        <div><h2 style={{ margin: "0 0 10px", font: "700 16px var(--font-sans)" }}>What you get</h2>
          <ul style={{ margin: 0, paddingLeft: 18, font: "400 15px/1.7 var(--font-sans)" }}><li>Results grouped by pharmacology, health risk factors, carrier status and traits</li><li>A map of where each gene sits on your chromosomes</li><li>A copy you can save as a report or a table</li></ul></div>
        <div><h2 style={{ margin: "0 0 10px", font: "700 16px var(--font-sans)" }}>What it can’t do</h2>
          <ul style={{ margin: 0, paddingLeft: 18, font: "400 15px/1.7 var(--font-sans)", color: "var(--text-muted)" }}><li>It is not a medical test or medical advice</li><li>It does not read whole genes, so a missing variant does not rule out risk</li><li>Markers outside the 14 checks are counted, not explained</li></ul></div>
      </div>
    </div>
  );
}
function AnalysisScreen({ step, setStep }) {
  const D = window.LDS_DEMO;
  const [phase, setPhase] = React.useState(step > 0 ? "results" : "idle");
  const [pct, setPct] = React.useState(0);
  const [open, setOpen] = React.useState(null);
  const [table, setTable] = React.useState(false);
  const [q, setQ] = React.useState("");
  React.useEffect(() => { if (step === 0 && phase === "results") { setPhase("idle"); setOpen(null); } }, [step]);
  const run = () => { setPhase("loading"); setPct(0); let v = 0; const t = setInterval(() => { v += 10; setPct(Math.min(v, 100)); if (v >= 100) { clearInterval(t); setTimeout(() => { setPhase("results"); setStep(1); }, 180); } }, 90); };
  if (phase !== "results") return <Intro phase={phase} pct={pct} run={run} />;
  const rows = allRows(D); const byId = id => rows.find(r => r.id === id);
  const n = s => rows.filter(r => r.state === s).length;
  const tech = r => r.rsid + " · " + (r.gt || "no reading");
  const list = (
    <div style={{ display: "flex", flexDirection: "column", gap: 56, minWidth: 0 }}>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", justifyContent: "space-between", gap: 16 }}>
        <div><h1 style={{ margin: 0, font: "400 40px/1.1 var(--font-serif)", letterSpacing: "-0.02em" }}>Your results</h1>
          <div style={{ marginTop: 8, font: "400 14px var(--font-mono)", color: "var(--text-muted)" }}>{D.file.name} · {D.file.format} · {D.file.build} · made-up example</div></div>
        <div style={{ display: "flex", gap: 8 }}><Button variant="secondary" size="sm" icon="download" onClick={() => setStep(2)}>Save a copy</Button><Button variant="ghost" size="sm" onClick={() => setStep(0)}>Use another file</Button></div>
      </div>
      <Alert tone="notice" title="Not finding a variant does not mean you have no risk.">Lucidase checks only the positions your DNA chip read. It does not read whole genes, and it cannot see larger changes such as missing or repeated stretches of DNA.</Alert>
      <ReportSection id="summary" title="Summary" aside="Each mark on the map is one of the checks. Select a mark to read that result.">
        <p style={{ margin: "0 0 20px", font: "400 18px/1.6 var(--font-serif)", maxWidth: "var(--measure-prose)" }}>Lucidase ran 13 checks on your file. A <Term definition="A change in the DNA letters at one position, compared with the most common version.">variant</Term> was found in {n("supported_and_observed")}, not found in {n("supported_not_observed")}, and {n("insufficient_evidence")} were unclear. {D.file.outside} other markers in your file were counted but not interpreted.</p>
        <Karyogram density loci={lociOf(rows)} selected={open && open.id} onSelect={id => setOpen(byId(id))} />
        <KaryogramLegend style={{ marginTop: 20, maxWidth: 560 }} items={[{ state: "supported_and_observed", count: n("supported_and_observed") }, { state: "supported_not_observed", count: n("supported_not_observed") }, { state: "not_tested_by_array", count: n("not_tested_by_array") }, { state: "insufficient_evidence", count: n("insufficient_evidence") }]} />
      </ReportSection>
      {window.LDS_GROUPS.map(g => { const rs = rows.filter(r => window.LDS_META[r.gene].group === g.id); return (
        <ReportSection key={g.id} id={g.id} title={g.title} aside={g.aside}>
          {rs.map(r => <FindingRow key={r.id} gene={r.gene} topic={window.LDS_META[r.gene].topic + (r.gene === "HFE" ? (r.rsid === "rs1800562" ? " — C282Y" : " — H63D") : "")} state={r.state} statement={r.statement} limitation={r.limitation} technical={tech(r)} onOpen={() => setOpen(r)} selected={open && open.id === r.id} />)}
        </ReportSection>); })}
      <ReportSection id="table" title="All results as a table" aside="The same results with the technical columns, for checking against other tools.">
        {!table ? <Button variant="secondary" size="sm" icon="table" onClick={() => setTable(true)}>Show the table</Button> : <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <SearchInput value={q} onChange={setQ} placeholder="Find a gene, marker or topic" />
          <DataTable caption="All results" rowKey="id" onRowClick={setOpen} selectedKey={open && open.id}
            rows={rows.filter(r => !q || (r.gene + r.rsid + window.LDS_META[r.gene].topic).toLowerCase().includes(q.toLowerCase()))}
            columns={[{ key: "state", label: "Result", render: r => <StateMark state={r.state} withLabel /> }, { key: "topic", label: "Topic", render: r => window.LDS_META[r.gene].topic }, { key: "gene", label: "Gene", mono: true }, { key: "rsid", label: "Marker", mono: true }, { key: "gt", label: "Genotype", mono: true, render: r => r.gt || <span className="lds-na">Not available</span> }, { key: "tier", label: "Tier", render: r => r.tier || <span className="lds-na">Not available</span> }]} /></div>}
      </ReportSection>
      {step === 2 && <ReportSection id="save" title="Save a copy" aside="Files are made on this device. Nothing is sent anywhere.">
        <div style={{ display: "flex", flexDirection: "column", gap: 14, maxWidth: "var(--measure-prose)" }}>
          <p style={{ margin: 0, font: "400 16px/1.55 var(--font-serif)" }}>Both copies include every result, its limitation and the scope notice above.</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}><Button icon="file-text">Save the report (.md)</Button><Button variant="secondary" icon="table">Save the table (.csv)</Button></div>
        </div></ReportSection>}
    </div>
  );
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 32, alignItems: "flex-start" }}>
      <div style={{ flex: "1 1 560px", minWidth: 0 }}>{list}</div>
      {open && <div style={{ flex: "0 1 var(--inspector-w)", minWidth: 320, alignSelf: "stretch" }}><window.RecordInspector rec={open} onClose={() => setOpen(null)} /></div>}
    </div>
  );
}
window.AnalysisScreen = AnalysisScreen;
})();
