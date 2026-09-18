/* Small shared helpers for the CMS; public website rendering lives in its own repo. */
(() => {
  'use strict';
  const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[character]));

  function image(source, alt, crop) {
    if (!source) return '';
    const url = new URL(source, location.href);
    if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) return '';
    if (crop) {
      const [x, y, width, height, originalWidth] = crop;
      return `<div class="sprite" style="aspect-ratio:${width}/${height}"><img src="${esc(url.href)}" alt="${esc(alt)}" style="width:${originalWidth/width*100}%;max-width:none;left:${-x/width*100}%;top:${-y/height*100}%" loading="lazy"></div>`;
    }
    return `<img src="${esc(url.href)}" alt="${esc(alt)}" loading="lazy">`;
  }

  function previewContent(value, key = '') {
    if (Array.isArray(value)) return value.map(item => previewContent(item, key));
    if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([name, child]) => [name, previewContent(child, name)]));
    if (['image', 'logo', 'heroLogo', 'opening', 'url'].includes(key) && typeof value === 'string' && /^(images|media)\//.test(value)) {
      return new URL(value, location.origin + '/').href;
    }
    return value;
  }

  window.MCSA = {esc, image, previewContent};
})();
