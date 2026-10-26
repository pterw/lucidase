Slim, static (not sticky) top bar: product name as text, page links, and local-only note. The theme override lives in the footer. Scrolls away with the page; includes a skip link.

```jsx
<AppHeader status={<LocalNote />} nav={<><NavLink active>Your results</NavLink><NavLink>Chromosome map</NavLink></>} />
```

- No wordmark artwork here: the wordmark appears once per page as a masthead with clear space (see Masthead). Never recolour it to fit chrome.
