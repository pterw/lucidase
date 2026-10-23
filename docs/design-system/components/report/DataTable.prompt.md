The findings table — condensed sticky headers, mono data cells, hairline rows, keyboard-activatable rows that open the Drawer.

```jsx
<DataTable caption="Observed findings" rowKey="rsid" onRowClick={open}
  columns={[{ key: "gene", label: "Gene" }, { key: "rsid", label: "rsID", mono: true }, { key: "state", label: "Coverage state", render: r => <Badge state={r.state} dot /> }]}
  rows={rows} />
```
- Put inside `<Panel flush>`. Missing cells use <NotAvailable/>.
