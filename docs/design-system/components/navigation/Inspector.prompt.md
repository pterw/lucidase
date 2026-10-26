Non-modal details pane docked beside the results (sticky, 440px column). The list stays visible and clickable; Esc or × closes. On narrow screens place it below the list.

```jsx
<div style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) var(--inspector-w)", gap: 32 }}>
  <Results />
  <Inspector open title="Clopidogrel (Plavix) response" subtitle="CYP2C19 · rs4244285 · chr10" onClose={close}>
    <InspectorSection title="What was found">…</InspectorSection>
  </Inspector>
</div>
```
- Replaces the modal drawer: inspecting must not hide what you are comparing against.
- InspectorSection = ruled block, never a nested box.
