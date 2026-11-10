// CloudFront Function (cloudfront-js-2.0), viewer-request, on the viciousshred.com distribution.
// Origin is GitHub Pages (adron.github.io, origin path /viciousshred.com).
var ASCII_PATHS = {
  "/2024/11/27/2025-releases-lining-up-already-%f0%9f%a4%98%f0%9f%8f%bb/": "/2024/11/27/2025-releases-lining-up-already/",
};

function handler(event) {
  var req = event.request;
  var host = req.headers.host ? req.headers.host.value : "";
  var uri = req.uri;

  // Canonical host: www -> apex (real 301, as WordPress did).
  if (host === "www.viciousshred.com") {
    return redirect("https://viciousshred.com" + uri + querystring(req));
  }

  // WordPress URLs GitHub Pages can't store (emoji in the path); keep in sync with ASCII_PATHS in scripts/wp_export.py.
  var moved = ASCII_PATHS[uri.toLowerCase()];
  if (moved) {
    return redirect(moved + querystring(req));
  }

  // WordPress served RSS at /feed/; serve the XML file so readers/FeedBurner get application/xml.
  if (uri === "/feed" || uri === "/feed/") {
    req.uri = "/feed.xml";
    return req;
  }

  // Directory URLs -> index.html at the origin, so GitHub never issues its own (github.io) redirects.
  if (uri.endsWith("/")) {
    req.uri = uri + "index.html";
    return req;
  }

  // Extensionless paths (e.g. /2013/11/02/slug) -> add the trailing slash WordPress used.
  var last = uri.substring(uri.lastIndexOf("/") + 1);
  if (last.indexOf(".") === -1) {
    return redirect(uri + "/" + querystring(req));
  }

  return req;
}

function redirect(location) {
  return {
    statusCode: 301,
    statusDescription: "Moved Permanently",
    headers: { location: { value: location }, "cache-control": { value: "max-age=3600" } },
  };
}

function querystring(req) {
  var parts = [];
  for (var key in req.querystring) {
    var q = req.querystring[key];
    var values = q.multiValue ? q.multiValue : [q];
    for (var i = 0; i < values.length; i++) {
      parts.push(values[i].value === "" ? key : key + "=" + values[i].value);
    }
  }
  return parts.length ? "?" + parts.join("&") : "";
}
