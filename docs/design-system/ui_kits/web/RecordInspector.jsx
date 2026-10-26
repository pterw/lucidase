(() => {
const { Inspector, InspectorSection, StateMark, DataList, SegmentedControl, ProbabilityBar, Button, Ligature, Term } = window.LucidaseDesignSystem_241006;
const MENDEL = { recessive: true, dominant: true };
function odds(r, partner) {
  const p = 0.5, q = partner === "wildtype" ? 0 : partner === "carrier" ? 0.5 : partner === "affected" ? 1 : r.af;
  if (q == null) return null;
  return { two: p * q * 100, one: (p * (1 - q) + (1 - p) * q) * 100, none: (1 - p) * (1 - q) * 100 };
}
function RecordInspector({ rec, onClose }) {
  const [partner, setPartner] = React.useState("unscreened");
  React.useEffect(() => setPartner("unscreened"), [rec && rec.id]);
  if (!rec) return null;
  const m = window.LDS_META[rec.gene] || {}; const mendel = MENDEL[rec.inheritance]; const o = odds(rec, partner);
  const opts = mendel ? [["unscreened","Unscreened"],["carrier","Carrier"],["affected","Affected"],["wildtype","No variant"]] : [["unscreened","Unscreened"],["carrier","One copy"],["affected","Two copies"],["wildtype","No variant"]];
  return (
    <Inspector open onClose={onClose} title={m.topic || rec.gene} subtitle={rec.gene + " · " + rec.rsid + " · chromosome " + m.chrom} meta={<StateMark state={rec.state} withLabel />}
      footer={<><span style={{ font: "400 13px var(--font-sans)", color: "var(--text-muted)" }}>Evidence tier {rec.tier || "not available"}</span>{rec.clinvar && <Button variant="link" size="sm" iconRight="arrow-up-right">ClinVar record</Button>}</>}>
      <InspectorSection title="What was found"><p style={{ margin: 0 }}>{rec.statement}</p>
        {rec.id === "APOE" && <Ligature left="rs429358 C/C" right="rs7412 C/C" result="APOE ε4/ε4" caption="One result built from two markers" />}</InspectorSection>
      {(rec.limitation || rec.caveat) && <InspectorSection title="What this can’t tell you"><p style={{ margin: 0 }}>{rec.limitation || rec.caveat}</p></InspectorSection>}
      {rec.gt && <InspectorSection title={mendel ? "If you have children" : "Passing it on"}>
        <p style={{ margin: 0, font: "400 14px/1.5 var(--font-sans)", color: "var(--text-muted)" }}>{mendel ? "The chance for each child, from your result and the other parent’s status you pick." : "The chance a child inherits the variant. This is not a disease figure."}</p>
        <SegmentedControl label="Other parent" size="sm" value={partner} onChange={setPartner} options={opts.map(([v, l]) => ({ value: v, label: l }))} />
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <ProbabilityBar label={mendel ? "Child affected (two copies)" : "Child gets two copies"} value={o && o.two} tone="insufficient" />
          <ProbabilityBar label={mendel ? "Child is a carrier (one copy)" : "Child gets one copy"} value={o && o.one} tone="array-gap" />
          <ProbabilityBar label="Child gets no copy" value={o && o.none} tone="not-observed" />
        </div>
        <p style={{ margin: 0, font: "400 13px/1.5 var(--font-sans)", color: "var(--text-muted)" }}>{partner === "unscreened" ? (rec.af != null ? "Unscreened uses how common the variant is in the population (" + rec.af.toFixed(3) + ")." : "No population frequency is available, so no figure is shown.") : "Assumes the other parent is: " + opts.find(x => x[0] === partner)[1].toLowerCase() + "."}</p>
      </InspectorSection>}
      <InspectorSection title="Technical details">
        <DataList columns={2} items={[{ term: "Genotype", value: rec.raw || rec.gt, reason: "No reading" }, { term: "Marker", value: rec.rsid }, { term: "ClinVar review", value: rec.clinvar, mono: false }, { term: "Population frequency", value: rec.af != null ? rec.af.toFixed(3) : null }]} />
      </InspectorSection>
    </Inspector>
  );
}
window.RecordInspector = RecordInspector;
})();
