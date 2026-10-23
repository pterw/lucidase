The single treatment for a missing value — muted italic "Not available"; never a placeholder number or an invented default.

```jsx
<StatChip label="Call rate" value={qc.callRate ?? <NotAvailable reason="Variants-only VCF" />} />
```
