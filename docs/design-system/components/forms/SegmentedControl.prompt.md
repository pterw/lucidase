Toggle group (aria-pressed) for one model input — e.g. the partner status in the offspring calculator.

```jsx
<SegmentedControl label="Partner" value={p} onChange={setP}
  options={["Unscreened","Carrier","Affected","Wild-type"]} />
```
- Selected = ink fill; equal-width segments; 2–5 options.
