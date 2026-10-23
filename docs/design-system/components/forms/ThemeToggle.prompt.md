Out-of-the-way theme override for the footer. The theme follows the device by default and most people never change it, so it is not a header feature.

```jsx
<AppFooter />   {/* includes ThemeToggle */}
```

- One muted text link: "Dark theme" or "Light theme" (the opposite of what's on screen). After an override a second link appears: "Use device setting".
- No-flash snippet for <head>: `<script>try{var t=localStorage.getItem('lucidase-theme');document.documentElement.dataset.theme=t||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light')}catch(e){}</script>`
