(() => {
const { ReportSection, Karyogram, KaryogramLegend, Button, DataTable, StateMark } = window.LucidaseDesignSystem_241006;
function KaryogramScreen() {
  const D = window.LDS_DEMO; const [file, setFile] = React.useState(false);
  const rows = D.records.concat(D.negative, D.gaps, D.insufficient);
  const seen = {}; const loci = rows.map(r => { const m = window.LDS_META[r.gene]; const off = seen[r.gene] ? 9 : 0; seen[r.gene] = 1; return { id: r.id, label: m.topic, chrom: m.chrom, pos: m.pos + (off ? 3 : 0), offset: off, state: file ? r.state : "reference" }; });
  const n = s => rows.filter(r => r.state === s).length;
  return (
    <>
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", justifyContent: "space-between", gap: 24 }}>
        <div style={{ maxWidth: 640 }}><h1 style={{ margin: 0, font: "400 40px/1.1 var(--font-serif)", letterSpacing: "-0.02em" }}>Chromosome map</h1>
          <p style={{ margin: "12px 0 0", font: "400 17px/1.6 var(--font-serif)", color: "var(--text-muted)" }}>Each dot is a stretch of chromosome about 4 million DNA letters long. With a file, bigger dots mean more of your markers sit there. The ringed marks are the genes this report checks.</p></div>
        <div style={{ display: "flex", gap: 10 }}>{!file ? <><Button icon="folder-open" onClick={() => setFile(true)}>Choose your DNA file</Button><Button variant="secondary" onClick={() => setFile(true)}>Try a made-up example file</Button></> : <Button variant="ghost" onClick={() => setFile(false)}>Clear the file</Button>}</div>
      </div>
      <figure style={{ margin: 0, display: "flex", flexDirection: "column", gap: 12 }}>
        <Karyogram density={file} loci={loci} />
        <figcaption style={{ font: "400 13px var(--font-sans)", color: "var(--text-muted)" }}>{file ? "sample-karyogram-23andme.txt · made-up example · drawn on GRCh38 chromosome lengths." : "No file yet: the chromosomes are drawn from the GRCh38 reference."}</figcaption>
      </figure>
      <ReportSection title="Key" aside={file ? "Your result for each gene this report checks." : "Choose a file to see your result for each gene."}>
        <KaryogramLegend style={{ maxWidth: 560 }} items={file ? [{ state: "supported_and_observed", count: n("supported_and_observed") }, { state: "supported_not_observed", count: n("supported_not_observed") }, { state: "not_tested_by_array", count: n("not_tested_by_array") }, { state: "insufficient_evidence", count: n("insufficient_evidence") }] : [{ state: "reference", label: "Genes this report checks", count: 12 }]} help={file} />
      </ReportSection>
      <ReportSection title="Genes on the map">
        <DataTable caption="Genes on the map" rowKey="id" rows={rows} columns={[{ key: "topic", label: "Topic", render: r => window.LDS_META[r.gene].topic }, { key: "gene", label: "Gene", mono: true }, { key: "chrom", label: "Chromosome", mono: true, render: r => window.LDS_META[r.gene].chrom }, { key: "state", label: "Your result", render: r => file ? <StateMark state={r.state} withLabel /> : <span className="lds-na">No file yet</span> }]} />
      </ReportSection>
    </>
  );
}
window.KaryogramScreen = KaryogramScreen;
})();
