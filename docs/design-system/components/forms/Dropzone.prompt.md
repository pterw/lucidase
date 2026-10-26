The file intake surface — keyboard-focusable, drag-and-drop, square dashed edge; the first thing on the analysis page.

```jsx
<Dropzone description="23andMe, AncestryDNA, MyHeritage or VCF. Your file is read in this browser and never uploaded." onFile={read}>
  <Button icon="folder-open">Choose a file</Button>
  <Button variant="secondary">Try a made-up example file</Button>
</Dropzone>
```
- Say what is accepted and that nothing is uploaded. No "Engineered for…" marketing.
