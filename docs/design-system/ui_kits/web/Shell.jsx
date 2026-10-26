(() => {
const { AppHeader, NavLink, LocalNote, ThemeToggle, AppFooter, StepNav } = window.LucidaseDesignSystem_241006;
function Shell({ page, onPage, theme, setTheme, step, onStep, children }) {
  return (
    <div style={{ minHeight: "100vh", display: "flex", flexDirection: "column" }}>
      <AppHeader
        nav={<><NavLink active={page === "analysis"} onClick={e => { e.preventDefault(); onPage("analysis"); }}>Your results</NavLink><NavLink active={page === "karyogram"} onClick={e => { e.preventDefault(); onPage("karyogram"); }}>Chromosome map</NavLink></>}
        status={<LocalNote />} />
      {page === "analysis" && <div style={{ borderBottom: "1px solid var(--border-default)" }}><div style={{ maxWidth: "var(--layout-max)", margin: "0 auto", padding: "12px var(--layout-gutter)" }}>
        <StepNav current={step} onStep={onStep} steps={[{ label: "Choose your file" }, { label: "Read your results", enabled: step > 0 }, { label: "Save a copy", enabled: step > 0 }]} /></div></div>}
      <main id="main" style={{ flex: 1, width: "100%", maxWidth: "var(--layout-max)", margin: "0 auto", padding: "40px var(--layout-gutter) 72px", boxSizing: "border-box", display: "flex", flexDirection: "column", gap: 48 }}>{children}</main>
      <AppFooter />
    </div>
  );
}
window.Shell = Shell;
})();
