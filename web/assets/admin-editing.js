/* Editing guidance follows the backend data contract; server validation remains authoritative. */
(() => {
  'use strict';
  const imageKeys = ['image', 'logo', 'heroLogo', 'opening'];
  const limits = {
    openingDuration: [100, 30000], contentWidth: [960, 1600], baseFontSize: [14, 20],
    sectionSpacing: [30, 110], cardRadius: [12, 48], heroCardWidth: [300, 520],
    heroSlope: [15, 80], presidentImageShare: [35, 55], presidentHeight: [420, 680],
    departmentHeight: [360, 680], departmentSpeed: [5, 50], contactQrSize: [80, 160],
    contactColumns: [2, 4], carouselSeconds: [4, 20]
  };
  const valueAt = (state, path) => path.split('.').reduce((value, key) => value?.[key], state);

  function validUrl(value, media = false) {
    if (typeof value !== 'string' || value.length > 4000 || /[\u0000-\u0020\\]/.test(value)) return false;
    if (!value) return true;
    if (/^[a-zA-Z][a-zA-Z0-9+.-]*:/.test(value)) {
      if (!/^https?:\/\/[^/]/i.test(value)) return false;
      try {
        const url = new URL(value);
        return ['http:', 'https:'].includes(url.protocol) && Boolean(url.hostname) && !url.username && !url.password;
      } catch { return false; }
    }
    if (value.includes('..')) return false;
    return media ? /^(images|media)\/[a-zA-Z0-9_.-]+\.(png|jpg|jpeg|gif|webp)$/.test(value)
      : /^([a-zA-Z0-9_-]+\.html(#[a-zA-Z0-9_-]+)?|#[a-zA-Z0-9_-]+)$/.test(value);
  }

  function validateField(path, value, state) {
    const parts = path.split('.');
    const key = parts.at(-1);
    if (key === 'url' && !validUrl(value)) return '请填写完整的 http:// 或 https:// 链接、站内页面（如 contact.html）或 #区块；也可留空。不要包含空格或账号密码。';
    if (imageKeys.includes(key) && !validUrl(value, true)) return '请上传图片，或填写完整的 HTTP(S) 图片网址、images/ 或 media/ 图片路径；也可留空。';
    if (typeof value === 'string' && Array.from(value).length > 12000) return '文字不能超过 12000 个字符。';
    if (key === 'email' && !/^[^\s<>"@]+@[^\s<>"@]+\.[^\s<>"@]+$/.test(value)) return '请填写有效邮箱，例如 hello@example.com。';
    if (key === 'date' && value && (!/^\d{4}-\d{2}-\d{2}$/.test(value) || !Number.isFinite(Date.parse(value)) || new Date(value).toISOString().slice(0, 10) !== value)) return '请填写有效日期，格式为 YYYY-MM-DD。';
    if (key === 'address' && Array.from(value).length > 500) return '商家地址不能超过 500 个字符。';
    if (key === 'latitude' || key === 'longitude') {
      const limit = key === 'latitude' ? 90 : 180;
      const sibling = valueAt(state, [...parts.slice(0, -1), key === 'latitude' ? 'longitude' : 'latitude'].join('.'));
      if (value !== null && (!Number.isFinite(value) || Math.abs(value) > limit)) return `请输入 -${limit} 到 ${limit} 的数字，或留空。`;
      if ((value === null) !== (sibling === null)) return '纬度和经度需同时填写，或同时留空。';
    }
    if (limits[key] && (!Number.isFinite(value) || value < limits[key][0] || value > limits[key][1] || (key === 'openingDuration' && !Number.isInteger(value)))) return `请输入 ${limits[key][0]} 到 ${limits[key][1]}${key === 'openingDuration' ? ' 的整数' : ' 的数字'}。`;
    if (/^posts\.\d+\.title\.zh$/.test(path) && valueAt(state, parts.slice(0, 2).join('.'))?.published && !value.trim()) return '发布文章前请填写中文标题；暂不发布可取消发布勾选。';
    if (/^merchants\.\d+\.name\.zh$/.test(path) && valueAt(state, parts.slice(0, 2).join('.'))?.published && !value.trim()) return '发布商家前请填写中文名称。';
    if (/^merchants\.\d+\.(region|category)$/.test(path) && valueAt(state, parts.slice(0, 2).join('.'))?.published && !state[key === 'region' ? 'regions' : 'categories']?.some(item => item.id === value)) return `发布商家前请选择有效${key === 'region' ? '地区' : '类别'}。`;
    return '';
  }

  function validateContent(state) {
    const errors = [];
    function visit(value, path) {
      if (value && typeof value === 'object') {
        Object.entries(value).forEach(([key, child]) => visit(child, path ? `${path}.${key}` : key));
      } else {
        const message = validateField(path, value, state);
        if (message) errors.push({path, message});
      }
    }
    visit(state, '');
    return errors;
  }

  function pathLabel(path, state, names, fieldNames) {
    const parts = path.split('.');
    let context = names[parts[0]] || parts[0];
    if (parts[0] === 'pages') context += ` / ${state.pages?.[parts[1]]?.title?.zh || parts[1]}`;
    else if (/^\d+$/.test(parts[1] || '')) context += ` / 第 ${Number(parts[1]) + 1} 条`;
    const key = ['zh', 'en', 'hant'].includes(parts.at(-1)) ? parts.at(-2) : parts.at(-1);
    if (parts.includes('paragraphs')) return `${context} / 正文段落 ${Number(parts.at(-2)) + 1}`;
    if (parts.includes('tags')) return `${context} / 标签 ${Number(parts.at(-2)) + 1}`;
    return `${context} / ${fieldNames[key] || key}`;
  }

  window.MCSAEditing = {imageKeys, limits, validUrl, validateField, validateContent, pathLabel};
})();
