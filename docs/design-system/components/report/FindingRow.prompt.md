One result in plain language: shape mark, what it is about, what was found, what it can’t tell you, then technical ids. The main way a newcomer reads results.

```jsx
<FindingRow topic="Clopidogrel (Plavix) response" gene="CYP2C19" state="supported_and_observed"
  statement="One copy of the *2 variant was found. It is linked to the drug working less well."
  limitation="Only one of many CYP2C19 variants is checked." technical="rs4244285 · G/A" onOpen={open} />
```
- Topic first, gene second, rsID last: meaning before jargon.
- Limitations are always visible, never hidden behind a tooltip.
