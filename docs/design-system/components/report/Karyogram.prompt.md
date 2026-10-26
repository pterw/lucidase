The brand figure: 24 chromosome columns of dots (4 Mb each) with the checked genes as haloed marks. Same visual language as the banner — use it as the overview of every results page.

```jsx
<Karyogram density loci={[{ id: "APOE", label: "APOE", chrom: "19", pos: 44.9, state: "supported_and_observed" }]} onSelect={open} />
```
- Mark shapes match StateMark (filled / ring / dashed ring). Demo density is seeded noise; real density comes from the file.
