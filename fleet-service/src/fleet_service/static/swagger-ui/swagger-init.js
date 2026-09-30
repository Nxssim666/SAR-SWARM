// The API docs page (M6): Swagger UI from the files next to this one, no CDN; a separate
// file because the gateway's Content-Security-Policy forbids inline scripts.
window.addEventListener('load', function () {
  window.ui = SwaggerUIBundle({
    url: document.body.dataset.openapi,
    dom_id: '#swagger-ui',
    deepLinking: true,
    persistAuthorization: false,
  });
});
