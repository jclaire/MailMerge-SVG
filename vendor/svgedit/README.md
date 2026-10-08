# SVG-Edit 7.4.2

Unmodified browser build of [SVG-Edit](https://github.com/svg-edit/svgedit) 7.4.2
(`svgedit@7.4.2` on npm), vendored so the template editor works on static
hosting such as GitHub Pages. No server-side processing is involved.

The MailMerge host page is `dist/editor/mailmerge.html`. It loads this build
and is the only file in this tree added for MailMerge-SVG. Upstream
`dist/editor/index.html` is the stock SVG-Edit entry and is not used by the app.

## License

SVG-Edit is MIT licensed. See `LICENSE-MIT.txt` and `AUTHORS`.

The published package also bundles components under other licenses
(Apache-2.0, LGPL-3.0-or-later, X11, and MIT OR GPL). `licenseInfo.json`
maps those licenses to upstream source paths. Corresponding source for this
version: <https://github.com/svg-edit/svgedit/tree/v7.4.2>.

Source maps, the package test suite, and the duplicate IIFE bundle are not
included.
