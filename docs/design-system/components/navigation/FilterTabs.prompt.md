Tablist (aria-selected) that switches the findings table between result sets — observed findings, not detected, not on array, insufficient evidence, and category filters.

```jsx
<FilterTabs value={f} onChange={setF} tabs={[{ id: "all", label: "Observed", count: 10 }, { id: "negative", label: "Not detected", count: 1 }]} />
```
- Plain names, no "(State 2)" codes. Counts are the analysis's own.
