# Vendored Swagger UI

`swagger-ui-dist` 5.33.0 (Apache-2.0, see `LICENSE` and `NOTICE`), from the npm registry:
`swagger-ui-bundle.js`, `swagger-ui.css` and `favicon-32x32.png`, unchanged. The station has
no Internet, so the API docs page (`/api/v1/docs`) serves these files itself (M6).
`swagger-init.js` is ours. To update, run `npm pack swagger-ui-dist@<version>` and copy
the same files.
