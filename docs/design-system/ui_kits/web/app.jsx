function App() {
  const [page, setPage] = React.useState(() => localStorage.getItem("lds-kit-page") || "analysis");
  const [step, setStep] = React.useState(0);
  const [theme, setTheme] = React.useState(() => { try { return localStorage.getItem("lucidase-theme") === "dark" ? "dark" : "light"; } catch (e) { return "light"; } });
  React.useEffect(() => { localStorage.setItem("lds-kit-page", page); }, [page]);
  return <Shell page={page} onPage={setPage} theme={theme} setTheme={setTheme} step={step} onStep={setStep}>{page === "analysis" ? <AnalysisScreen step={step} setStep={setStep} /> : <KaryogramScreen />}</Shell>;
}
ReactDOM.createRoot(document.getElementById("root")).render(<App />);
