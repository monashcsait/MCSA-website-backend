/* Chinese-only CMS. All changes stay in memory until Save is confirmed by the server. */
(() => {
  'use strict';
  const {
    esc,
    image
  } = window.MCSA;
  let state, revision, csrf, currentUser, accounts = [], dirty = false, busy = false;
  let validationErrors = [];
  const editing = window.MCSAEditing;
  let section = 'posts';
  const root = () => document.querySelector('#admin-root');
  const isSuper = () => currentUser?.role === 'super_admin';
  const can = permission => isSuper() || currentUser?.permissions?.includes(permission);
  const accountPermissions = {
    'site.read': '查看网站内容',
    'site.write': '编辑并发布网站内容',
    'merchant.read': '查看折扣商家、地区与类别',
    'merchant.write': '编辑并发布折扣商家',
    'media.upload': '上传图片',
    'backup.download': '下载内容备份'
  };
  const names = {
    posts: '活动与文章',
    pages: '页面文字',
    departments: '部门与招新链接',
    team: '现任主席团',
    terms: '历任主席团',
    merchants: '折扣商家',
    regions: '商家地区',
    categories: '商家种类',
    sponsors: '年度赞助',
    socials: '联系与社交媒体',
    footerLinks: '底部链接',
    settings: '网站设置',
    layout: '配色与布局',
    homeSections: '首页区块排序',
    interfaceText: '按钮与界面文字'
  };
  const fieldNames = {
    title: '标题',
    text: '正文',
    name: '名称',
    intro: '部门介绍',
    recruitment: '招新说明',
    role: '职位',
    description: '介绍',
    url: '超链接（留空则不跳转）',
    image: '图片',
    address: '商家详细地址',
    latitude: '纬度',
    longitude: '经度',
    account: '账号原文',
    date: '发布日期',
    published: '发布到网站',
    year: '排序年份（越大越靠前）',
    logo: '左上角标志与网站图标',
    heroLogo: '首页大标志',
    opening: '开场动画',
    openingDuration: '开场时长（毫秒）',
    footer: '版权文字',
    email: '联系邮箱',
    heroBlurb: '首页标志下方文字',
    keywords: '标签（用竖线 ｜ 分隔）',
    departmentOverview: '部门区默认总介绍',
    departmentOverviewTitle: '部门区默认标题',
    departmentOverviewTags: '默认标签（用竖线 ｜ 分隔）',
    departmentHint: '部门标题下的说明',
    departmentButton: '部门详情按钮模板（{name} 自动替换为部门名称）',
    departmentReset: '旧版概览文字（新版前台不使用）',
    contentWidth: '内容最大宽度（960—1600像素）',
    baseFontSize: '正文基础字号（14—20像素）',
    sectionSpacing: '区块上下留白（30—110像素）',
    cardRadius: '主要卡片圆角（12—48像素）',
    primaryColor: '主题红色',
    backgroundColor: '背景渐变浅色',
    heroCardWidth: '首页白卡宽度（300—520像素）',
    heroSlope: '红色背景斜切位置（15—80）',
    presidentImageShare: '主席团照片宽度占比（35—55）',
    presidentHeight: '主席团桌面卡片高度（420—680像素）',
    departmentHeight: '部门列表桌面高度（360—680像素）',
    departmentSpeed: '部门滚动速度（5—50像素/秒）',
    contactQrSize: '二维码框尺寸（80—160像素）',
    contactColumns: '电脑端二维码列数（2—4）',
    carouselSeconds: '主席团轮播间隔（4—20秒）',
    departmentDirection: '部门自动滚动方向',
    departmentAutoplay: '启用部门自动滚动'

  };
  const tri = () => ({
    zh: '',
    en: '',
    hant: ''
  });
  const uid = () => 'item-' + crypto.randomUUID();
  const templates = {
    posts: () => ({
      id: uid(),
      page: 'latest-events',
      title: tri(),
      text: tri(),
      image: '',
      url: '',
      published: false,
      date: new Date().toISOString().slice(0, 10),
      crop: null
    }),
    departments: () => ({
      id: uid(),
      name: tri(),
      intro: tri(),
      recruitment: tri(),
      keywords: tri(),
      image: '',
      url: ''
    }),
    team: () => ({
      name: tri(),
      role: tri(),
      description: tri(),
      image: '',
      url: '',
      tags: []
    }),
    terms: () => ({
      id: uid(),
      name: tri(),
      year: new Date().getFullYear() - 1,
      members: []
    }),
    member: () => ({
      name: tri(),
      role: tri(),
      image: '',
      url: ''
    }),
    merchants: () => ({
      id: uid(),
      name: tri(),
      text: tri(),
      image: '',
      url: '',
      region: state.regions[0]?.id || '',
      category: state.categories[0]?.id || '',
      address: '',
      latitude: null,
      longitude: null,
      published: false
    }),
    sponsors: () => ({
      id: uid(),
      name: tri(),
      image: '',
      url: ''
    }),
    socials: () => ({
      id: uid(),
      name: tri(),
      account: '',
      placement: 'qr',
      image: '',
      url: '',
      crop: null
    }),
    footerLinks: () => ({
      id: uid(),
      name: tri(),
      url: ''
    }),
    regions: () => ({
      id: uid(),
      name: tri()
    }),
    categories: () => ({
      id: uid(),
      name: tri()
    })
  };

  async function api(path, options = {}) {
    const headers = {
      ...options.headers
    };
    if (!(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
    if (csrf) headers['X-CSRF-Token'] = csrf;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), path.includes('/admin/') && options.method === 'PUT' ? 120000 : 45000);
    let response;
    try {
      response = await fetch('/api' + path, {...options, headers, signal: controller.signal});
    } catch (error) {
      throw Error(error.name === 'AbortError'
        ? '请求等待时间过长，当前修改仍保留。保存请求可能已经到达服务器，请先导出修改，再核对保存结果。'
        : '无法连接服务器，当前修改仍保留。请检查网络；离开前可导出未保存内容。');
    } finally { clearTimeout(timer); }
    let result;
    try {
      result = await response.json();
    } catch {
      throw Error(response.status === 413 ? '图片不能超过 12 MiB（约 12.6 MB）。' : '服务器返回了无法读取的响应，当前修改仍保留。请检查后台服务是否正常运行。');
    }
    if (!response.ok) {
      const errors = {
        invalid_login: '账号或密码不正确。',
        revision_conflict: '其他管理员已经更新内容。当前修改仍保留，请先导出未保存内容，再刷新核对最新版本。系统不会自动合并。',
        login_required: '登录已过期，当前修改仍保留。请先导出未保存内容，再刷新页面重新登录。',
        csrf_failed: '登录验证失效，当前修改仍保留。请先导出未保存内容，再刷新页面重新登录。',
        invalid_content: '内容格式有误，请检查链接、邮箱、日期和必填项。',
        invalid_merchant_address: '商家地址最多可填写 500 个字符。',
        invalid_merchant_published: '商家的发布状态无效，请刷新页面后重试。',
        invalid_merchant_coordinates: '请同时填写纬度和经度，并检查纬度为 -90 到 90、经度为 -180 到 180。',
        too_many_attempts: '登录尝试过多，请五分钟后重试。',
        invalid_image: '图片内容无效，或超过 2400 万像素／GIF 1000 帧；请使用 PNG、JPEG、GIF 或 WebP。',
        file_too_large: '图片不能超过 12 MiB（约 12.6 MB）。',
        server_error: '服务器暂时无法完成操作，当前修改仍保留。请稍后重试或联系后端负责人。',
        forbidden: '当前账号没有此功能的权限。',
        invalid_username: '账号名需为 3—32 位英文字母、数字、点、下划线或短横线。',
        invalid_password: '密码至少需要 12 个字符。',
        invalid_permissions: '权限组合无效；编辑权限需要对应查看权限，上传图片需要网站或商家查看权限。',
        invalid_merchant_reference: '发布商家前请填写名称，并选择有效地区和类别。',
        invalid_role: '账号角色或启用状态无效。',
        username_taken: '账号名已被使用。',
        last_super_admin: '至少需要保留一位启用中的超级管理员。'
      };
      throw Error(errors[result.error] || '操作失败，请稍后重试。');
    }
    return result;
  }

  function status(message, error = false) {
    const element = document.querySelector('#cms-status');
    if (element) {
      element.textContent = message;
      element.classList.toggle('error', error);
      element.setAttribute('role', error ? 'alert' : 'status');
    }
  }

  function markDirty() {
    dirty = true;
    status('有未保存的修改。');
  }

  function setBusy(active) {
    busy = active;
    root().setAttribute('aria-busy', String(active));
    root().querySelector('.cms-layout')?.toggleAttribute('inert', active);
    root().querySelectorAll('.cms-toolbar button').forEach(button => {
      button.disabled = active || (button.id === 'export-draft' && !dirty);
    });
  }

  function field(path, value, label) {
    const message = editing.validateField(path, value, state);
    const errorId = 'cms-error-' + encodeURIComponent(path);
    return `<div class="cms-field-group" data-field-group="${esc(path)}">${rawField(path,value,label)}<small class="cms-field-error" id="${esc(errorId)}" ${message?'':'hidden'}>${esc(message)}</small></div>`;
  }

  function get(path) {
    return path.split('.').reduce((value, key) => value[key], state);
  }

  function set(path, value) {
    const keys = path.split('.');
    const last = keys.pop();
    get(keys.join('.'))[last] = value;
    markDirty();
  }

  function rawField(path, value, label) {
    const key = path.split('.').pop();
    label = label || fieldNames[key] || key;
    if (value && typeof value === 'object' && !Array.isArray(value) && 'zh' in value) {
      const ready = value.en && value.hant;
      return `<label class="cms-field">${esc(label)}<textarea data-path="${path}.zh">${esc(value.zh)}</textarea><small>${ready?'英文与繁体内容已就绪；修改后保存会同步更新。':'保存时自动翻译；繁体中文本地生成；英文未配置服务时标记待翻译。'}</small></label>`;
    }
    if (['image', 'logo', 'heroLogo', 'opening'].includes(key)) {
      return `<div class="cms-field"><label>${esc(label)}<input data-path="${path}" value="${esc(value)}" placeholder="上传图片或填写图片网址"></label><div class="upload-row"><span class="cms-thumbnail">${image(value,label,get(path.split('.').slice(0,-1).join('.'))?.crop)}</span>${can('media.upload')?`<label class="button">${value?'替换图片':'上传图片'}<input class="upload-file" data-upload="${path}" type="file" accept="image/png,image/jpeg,image/gif,image/webp"></label>`:''}<button type="button" data-clear="${path}" ${value?'':'disabled'}>清除图片</button></div><small>支持 PNG、JPEG、GIF、WebP；单图最多 12 MiB（约 12.6 MB）、2400 万像素，GIF 最多 1000 帧。上传／替换／清除后需保存才生效。</small><small class="cms-image-status">${value?'':'尚未设置图片。'}</small></div>`;
    }
    if (key === 'placement' || key === 'departmentDirection') {
      const options = key === 'placement' ? [
        ['qr', '二维码区'],
        ['account', '底部账号文字'],
        ['hidden', '暂不显示']
      ] : [
        ['up', '向上滚动'],
        ['down', '向下滚动']
      ];
      return `<label class="cms-field">${key==='placement'?'联系方式展示位置':fieldNames[key]}<select data-path="${path}">${options.map(([id,name])=>`<option value="${id}" ${value===id?'selected':''}>${name}</option>`).join('')}</select></label>`;
    }
    if (key === 'primaryColor' || key === 'backgroundColor') return `<label class="cms-field">${label}<input type="color" data-path="${path}" value="${esc(value)}"></label>`;
    if (key === 'page' || key === 'region' || key === 'category') {
      const options = key === 'page' ? Object.entries(state.pages).map(([id, p]) => ({
        id,
        name: p.title
      })) : state[key === 'region' ? 'regions' : 'categories'];
      return `<label class="cms-field">${key==='page'?'所属页面':key==='region'?'地区':'种类'}<select data-path="${path}"><option value="">请选择</option>${options.map(item=>`<option value="${esc(item.id)}" ${item.id===value?'selected':''}>${esc(item.name.zh)}</option>`).join('')}</select></label>`;
    }
    if (key === 'latitude' || key === 'longitude') {
      const limit = key === 'latitude' ? 90 : 180;
      return `<label class="cms-field">${esc(label)}<input data-path="${path}" type="number" step="any" min="-${limit}" max="${limit}" value="${esc(value ?? '')}" placeholder="可留空">${key==='latitude'?'<small>纬度和经度需同时填写；留空时商家不会显示地图标记。</small>':''}</label>`;
    }
    if (key === 'address') return `<label class="cms-field">${esc(label)}<input data-path="${path}" value="${esc(value)}" maxlength="500" placeholder="可留空"></label>`;
    if (key === 'url') return `<label class="cms-field">${esc(label)}<input data-path="${path}" value="${esc(value)}" inputmode="url" placeholder="https://example.com 或 contact.html"><small>支持完整 HTTP(S) 网址、站内 .html 页面或 #区块；留空则不跳转。</small></label>`;
    if (key === 'departmentReset') return `<label class="cms-field">${esc(label)}<input data-path="${path}" value="${esc(value)}"><small>旧字段保留兼容；隐藏／删除待负责人确认。</small></label>`;
    if (typeof value === 'boolean') return `<label class="cms-check"><input data-path="${path}" type="checkbox" ${value?'checked':''}>${esc(label)}</label>`;
    return `<label class="cms-field">${esc(label)}<input data-path="${path}" type="${typeof value==='number'?'number':key==='date'?'date':'text'}" value="${esc(value)}"></label>`;
  }

  function objectFields(path, object) {
    const order = ['name', 'title', 'page', 'date', 'role', 'description', 'text', 'intro', 'recruitment', 'year', 'image', 'region', 'category', 'address', 'latitude', 'longitude', 'url', 'account', 'published'];
    return Object.entries(object).sort(([first], [second]) => {
      const position = key => order.includes(key) ? order.indexOf(key) : 100;
      return position(first) - position(second);
    }).filter(([key]) => !['id', 'crop', 'tags', 'members'].includes(key)).map(([key, value]) => field(path + '.' + key, value)).join('');
  }

  function editorCard(path, entry, index, kind) {
    const title = entry.name?.zh || entry.title?.zh || '未命名内容';
    const list = get(path.split('.').slice(0,-1).join('.'));
    return `<details class="editor-card" ${index===0?'open':''}><summary>${index+1}. ${esc(title)}${['posts','merchants'].includes(kind)&&!entry.published?' · 草稿':''}</summary><div class="editor-body">${objectFields(path,entry)}${kind==='terms'?`<h3>本届成员</h3>${entry.members.map((member,i)=>editorCard(path+'.members.'+i,member,i,'member')).join('')}<button type="button" data-add-member="${path}.members">添加成员</button>`:''}<div class="editor-actions"><button type="button" data-move="${path}" data-direction="-1" ${index===0?'disabled':''}>上移</button><button type="button" data-move="${path}" data-direction="1" ${index===list.length-1?'disabled':''}>下移</button><button type="button" class="danger" data-delete="${path}">删除这条内容</button></div></div></details>`;
  }

  function contentEditor() {
    if (section === 'homeSections') return `<p class="cms-hint">用上下按钮调整首页次序；关闭显示会隐藏该区块。导航保持原有内容。</p>${state.homeSections.map((item,index)=>`<div class="section-order-row"><strong>${esc(item.name.zh)}</strong><label><input type="checkbox" data-path="homeSections.${index}.visible" ${item.visible?'checked':''}>显示</label><button data-move="homeSections.${index}" data-direction="-1">上移</button><button data-move="homeSections.${index}" data-direction="1">下移</button></div>`).join('')}`;

    if (['settings', 'layout', 'interfaceText'].includes(section)) return `${section==='interfaceText'?'<label class="cms-field">查找界面文案<input id="cms-field-search" type="search" placeholder="输入原文或关键词"></label>':''}<div class="editor-body">${objectFields(section,state[section])}</div>`;
    if (section === 'pages') return Object.entries(state.pages).map(([key, page]) => `<details class="editor-card"><summary>${esc(page.title.zh)}</summary><div class="editor-body">${field('pages.'+key+'.title',page.title)}${page.paragraphs.map((text,i)=>`<div>${field('pages.'+key+'.paragraphs.'+i,text,'正文段落 '+(i+1))}<button type="button" data-delete="pages.${key}.paragraphs.${i}">删除段落</button></div>`).join('')}<button type="button" data-add-paragraph="${key}">添加段落</button><p class="cms-hint">图片、附加文章和超链接请到“活动与文章”中选择此页面添加。关于我们在首页显示。</p></div></details>`).join('');
    const entries = state[section];
    const hint = section==='departments'?'每个部门只需填写一个超链接：首页详情按钮、招新页面详情按钮和导航栏“部门招新”同步使用。修改并保存发布后，刷新官网即可生效。留空时详情按钮不可点击，导航不跳转。'
      : section==='terms'?'按排序年份倒序显示。现任资料在“现任主席团”编辑；每届可继续添加成员。'
      : section==='posts'?'首页显示最新三个已发布活动。相同日期以列表靠后的内容为新。取消勾选发布可保留为草稿。'
      : section==='merchants'?'新商家默认为草稿。勾选“发布到网站”并保存后才公开；纬度和经度可同时留空，需要地图标记时再填写并核对。'
      : '修改后点击“保存并发布”才会写入网站；没有独立发布开关的栏目保存后进入公开内容。';
    return `<button type="button" class="button primary" id="add-entry">添加${names[section]}</button><p class="cms-hint">${hint}</p>${entries.map((entry,index)=>editorCard(section+'.'+index,entry,index,section)).join('')}`;
  }

  function accountForm(account) {
    const existing = Boolean(account);
    const selected = account?.permissions || [];
    return `<form class="account-form editor-card" data-account-id="${existing?account.id:'new'}"><div class="editor-body"><h3>${existing?esc(account.username):'创建账号'}</h3><label class="cms-field">账号名<input name="username" value="${esc(account?.username || '')}" pattern="[A-Za-z0-9_.-]{3,32}" minlength="3" maxlength="32" autocomplete="off" required></label><label class="cms-field">${existing?'设置新密码（留空则不修改）':'初始密码'}<input name="password" type="password" minlength="12" maxlength="1024" autocomplete="new-password" ${existing?'':'required'}></label><label class="cms-field">角色<select name="role"><option value="admin" ${account?.role==='admin'?'selected':''}>普通管理员</option><option value="super_admin" ${account?.role==='super_admin'?'selected':''}>超级管理员</option></select></label><label class="cms-check"><input name="active" type="checkbox" ${account?.active===false?'':'checked'}>启用账号</label><fieldset class="account-permissions"><legend>普通管理员权限</legend><p class="cms-hint">超级管理员拥有全部权限；网站编辑需勾选网站查看，商家编辑需勾选商家查看，上传图片需至少一项查看权限。</p>${Object.entries(accountPermissions).map(([key,label])=>`<label class="cms-check"><input name="permissions" type="checkbox" value="${key}" ${selected.includes(key)?'checked':''}>${label}</label>`).join('')}</fieldset><button class="button primary" type="submit">${existing?'保存账号':'创建账号'}</button></div></form>`;
  }

  function accountEditor() {
    return `<p class="cms-hint">账号停用或权限变更后，该账号的现有登录会话会失效。至少保留一位启用中的超级管理员。</p>${accountForm(null)}<h3>现有账号</h3>${accounts.map(accountForm).join('')}`;
  }

  function validationSummary() {
    return validationErrors.length ? `<strong>请先检查以下 ${validationErrors.length} 处内容，修改尚未保存：</strong><ul>${validationErrors.map(error=>`<li><button type="button" data-show-error="${esc(error.path)}">${esc(editing.pathLabel(error.path,state,names,fieldNames))}</button>：${esc(error.message)}</li>`).join('')}</ul>` : '';
  }

  function revealField(path) {
    section = path.split('.')[0];
    render();
    const input = [...root().querySelectorAll('[data-path]')].find(element => element.dataset.path === path);
    if (!input) return;
    for (let parent = input.parentElement; parent; parent = parent.parentElement) {
      if (parent.tagName === 'DETAILS') parent.open = true;
      parent.hidden = false;
    }
    input.focus();
    input.scrollIntoView({block: 'center'});
  }

  function render() {
    const sections = can('site.read') ? Object.entries(names) : can('merchant.read') ? ['merchants', 'regions', 'categories'].map(key => [key, names[key]]) : [];
    if (isSuper()) sections.push(['accounts', '账号与权限']);
    if (!sections.length) section = '';
    else if (!sections.some(([key]) => key === section)) section = sections[0][0];
    const merchantSection = ['merchants', 'regions', 'categories'].includes(section);
    const editing = section !== 'accounts' && (can('site.read') || (merchantSection && can('merchant.read')));
    const mayEdit = can('site.write') || (merchantSection && can('merchant.write'));
    const editor = section === 'accounts' && isSuper() ? accountEditor()
      : editing ? mayEdit ? contentEditor() : `<p class="cms-hint">当前账号仅有查看权限。</p><fieldset disabled>${contentEditor()}</fieldset>`
      : '<p class="cms-hint">当前账号没有内容管理权限。</p>';
    if (validationErrors.length) validationErrors = window.MCSAEditing.validateContent(state);
    root().innerHTML = `<section class="cms">
      <div class="cms-heading"><div><h1>网站管理后台</h1><p>${esc(currentUser?.username || '')} · ${isSuper()?'超级管理员':'普通管理员'}</p></div><a class="button" href="${esc(window.MCSA_CONFIG.frontendUrl)}" target="_blank" rel="noopener noreferrer">查看网站 ↗</a></div>
      <div class="cms-toolbar" aria-label="内容操作">
        ${editing&&mayEdit?'<button class="button primary" id="save-site">保存并发布</button>':''}
        ${editing&&can('site.read')?'<button class="button" id="preview-site">预览未保存内容</button>':''}
        ${state?`<button type="button" id="export-draft" ${dirty?'':'disabled'}>导出未保存内容</button>`:''}
        ${can('backup.download')?'<a class="button" href="/api/backup">下载内容备份</a>':''}<button id="logout">退出登录</button>
      </div>
      <p id="cms-status" role="status">${dirty?'有未保存的修改。':'功能已载入。'}</p>
      <div id="cms-validation" class="cms-validation" role="alert" ${validationErrors.length?'':'hidden'}>${validationSummary()}</div>
      <div class="cms-layout"><p class="cms-nav-hint">左右滑动切换管理栏目</p><nav class="cms-tabs" aria-label="管理栏目">${sections.map(([key,name])=>`<button type="button" data-section="${key}" class="${section===key?'selected':''}" aria-pressed="${section===key}">${name}</button>`).join('')}</nav><div class="cms-editor"><h2>${section==='accounts'?'账号与权限':names[section]||'可用功能'}</h2>${editor}</div></div>
    </section>`;
    bind();
    setBusy(busy);
  }

  function remove(path) {
    if (busy || !confirm(`确定删除「${window.MCSAEditing.pathLabel(path,state,names,fieldNames)}」？保存后才会生效。`)) return;
    const parts = path.split('.');
    const index = Number(parts.pop());
    const list = get(parts.join('.'));
    if (parts[0] === 'team' && list.length === 1) {
      status('现任主席团至少保留一位成员。', true);
      return;
    }
    if (['regions', 'categories'].includes(parts[0])) {
      const field = parts[0] === 'regions' ? 'region' : 'category';
      if (state.merchants.some(item => item[field] === list[index].id)) {
        status('这个筛选项仍被商家使用，请先修改相关商家的分类。', true);
        return;
      }
    }
    list.splice(index, 1);
    markDirty();
    render();
  }

  function exportDraft() {
    if (!state || !dirty || busy) return;
    const blob = new Blob([JSON.stringify({format:'mcsa-content-draft-v1', revision, data:state}, null, 2)], {type:'application/json;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `MCSA-未保存内容-${new Date().toISOString().replace(/[:.]/g,'-')}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
    status('当前编辑内容已导出到文件，网站尚未保存这些修改。重新登录后可参照文件恢复编辑。');
  }

  function previewSite() {
      if (busy) return;
      let frontend;
      try {
        frontend = new URL(window.MCSA_CONFIG.frontendUrl);
        if (!['http:','https:'].includes(frontend.protocol) || frontend.username || frontend.password) throw Error();
      } catch { status('预览网址未正确配置，请联系负责人确认前端地址。',true); return; }
      const dialog = document.createElement('dialog');
      dialog.className = 'cms-preview';
      dialog.setAttribute('aria-labelledby','cms-preview-title');
      const options = Object.entries(state.pages).map(([key,value])=>({id:key, name:value.title.zh || key}));
      options.push({id:'departments',name:'部门列表'});
      state.posts.forEach((post,index)=>options.push({id:'post:'+post.id,name:`文章 ${index+1}：${post.title.zh || '未命名'}${post.published?'':'（草稿）'}`}));
      const defaults = {posts:state.posts[0]?'post:'+state.posts[0].id:'latest-events',departments:'departments',team:'home',terms:'presidents',merchants:'discounts',socials:'contact',sponsors:'sponsors'};
      let selected = defaults[section] || 'home';
      if (section === 'pages') selected = root().querySelector('.editor-card[open] [data-path]')?.dataset.path.split('.')[1] || 'home';
      dialog.innerHTML = `<div class="cms-preview-heading"><strong id="cms-preview-title">预览当前编辑内容</strong><button type="button" class="cms-preview-close">关闭预览</button></div><label class="cms-preview-choice">选择页面或文章<select>${options.map(option=>`<option value="${esc(option.id)}" ${option.id===selected?'selected':''}>${esc(option.name)}</option>`).join('')}</select></label><p class="cms-preview-status" role="status">正在连接预览…</p><iframe title="当前编辑内容预览"></iframe>`;
      const frame = dialog.querySelector('iframe');
      const selector = dialog.querySelector('select');
      const hint = dialog.querySelector('.cms-preview-status');
      let timeout;
      let previewSnapshot;
      function start() {
        clearTimeout(timeout);
        previewSnapshot = structuredClone(state);
        previewSnapshot.merchants = previewSnapshot.merchants.filter(item=>item.published);
        const id = selector.value;
        const article = id.startsWith('post:') ? previewSnapshot.posts.find(post=>post.id===id.slice(5)) : null;
        if (article) article.published = true;
        const file = article?'article.html':id==='home'?'index.html':id+'.html';
        const previewUrl = new URL(file,frontend);
        previewUrl.searchParams.set('preview','1');
        if (article) previewUrl.searchParams.set('id',article.id);
        hint.textContent = '正在连接预览…';
        hint.classList.remove('error');
        frame.src = previewUrl.href;
        timeout = setTimeout(()=>{
          hint.textContent = '未连接到预览。请确认前端服务已启动，并且前端 API 地址指向当前后台；也可重新选择页面重试。编辑内容仍保留。';
          hint.classList.add('error');
        },10000);
      }
      function receive(event) {
        if (event.source !== frame.contentWindow || event.origin !== frontend.origin || event.data?.type !== 'mcsa-preview-ready') return;
        clearTimeout(timeout);
        frame.contentWindow.postMessage({type: 'mcsa-preview-content', content: window.MCSA.previewContent(previewSnapshot)}, frontend.origin);
        hint.classList.remove('error');
        hint.textContent = selector.value.startsWith('post:') ? '已传入当前文章内容；草稿也可预览效果。本次预览不会保存或公开内容。' : '已传入当前编辑内容；列表按当前发布状态展示。本次预览不会保存或发布。';
      }
      window.addEventListener('message', receive);
      document.body.append(dialog);
      dialog.showModal();
      function cleanup() {
        clearTimeout(timeout);
        window.removeEventListener('message', receive);
        dialog.remove();
        document.querySelector('#preview-site')?.focus();
      }
      dialog.querySelector('.cms-preview-close').onclick = () => dialog.close();
      dialog.addEventListener('close',cleanup,{once:true});
      selector.onchange = start;
      start();
  }

  function refreshValidation() {
    root().querySelectorAll('[data-path]').forEach(input=>{
      const message = editing.validateField(input.dataset.path,get(input.dataset.path),state);
      const error = document.getElementById('cms-error-'+encodeURIComponent(input.dataset.path));
      input.setAttribute('aria-invalid',String(Boolean(message)));
      if (error) { error.hidden = !message; error.textContent = message; }
    });
    if (validationErrors.length) {
      validationErrors = editing.validateContent(state);
      const summary = document.querySelector('#cms-validation');
      summary.hidden = !validationErrors.length;
      summary.innerHTML = validationSummary();
    }
  }

  function bindImageHints() {
    root().querySelectorAll('.cms-thumbnail img').forEach(img=>{
      if (img.dataset.feedbackBound) return;
      img.dataset.feedbackBound = 'true';
      const hint = img.closest('.cms-field').querySelector('.cms-image-status');
      const loaded = () => {hint.textContent='图片缩略图已载入。';};
      const failed = () => {hint.textContent='无法加载图片，请检查图片网址；当前编辑值仍保留。';};
      img.addEventListener('error',failed);
      img.addEventListener('load',loaded);
      if (img.complete) (img.naturalWidth?loaded:failed)();
    });
  }

  function bind() {
    document.querySelector('#preview-site')?.addEventListener('click',previewSite);
    document.querySelector('#export-draft')?.addEventListener('click',exportDraft);
    document.querySelector('#cms-validation').onclick = event => {
      const button = event.target.closest('[data-show-error]');
      if (button) revealField(button.dataset.showError);
    };

    root().querySelectorAll('[data-path]').forEach(input => input.oninput = () => {
      if (busy) return;
      const current = get(input.dataset.path);
      const key = input.dataset.path.split('.').pop();
      const coordinate = key === 'latitude' || key === 'longitude';
      const value = input.type === 'checkbox' ? input.checked
        : coordinate ? (input.value === '' ? null : Number(input.value))
        : typeof current === 'number' ? Number(input.value) : input.value;
      set(input.dataset.path, value);
      if (editing.imageKeys.includes(key)) {
        const parent = get(input.dataset.path.split('.').slice(0,-1).join('.'));
        if ('crop' in parent) parent.crop = null;
      }
      document.querySelector('#export-draft').disabled = false;
      refreshValidation();
    });
    root().querySelectorAll('[data-path]').forEach(input=>{
      const path = input.dataset.path;
      input.id = 'cms-field-'+encodeURIComponent(path);
      const error = document.getElementById('cms-error-'+encodeURIComponent(path));
      if (error) input.setAttribute('aria-describedby',error.id);
      if (editing.imageKeys.includes(path.split('.').at(-1))) input.onchange = () => {
        const group = input.closest('.cms-field-group');
        const value = get(path);
        group.querySelector('.cms-thumbnail').innerHTML = image(value,fieldNames[path.split('.').at(-1)],get(path.split('.').slice(0,-1).join('.'))?.crop);
        group.querySelector('[data-clear]').disabled = !value;
        group.querySelector('.cms-image-status').textContent = value ? '正在检查图片…' : '尚未设置图片。';
        bindImageHints();
      };
    });
    refreshValidation();
    bindImageHints();
    const search = document.querySelector('#cms-field-search');
    if (search) search.oninput = () => {
      const query = search.value.trim().toLocaleLowerCase();
      root().querySelectorAll('.cms-editor > .editor-body > .cms-field-group').forEach(group=>{
        group.hidden = Boolean(query) && !group.textContent.toLocaleLowerCase().includes(query);
      });
    };
    root().querySelectorAll('[data-section]').forEach(button => button.onclick = () => {
      section = button.dataset.section;
      render();
    });
    root().querySelectorAll('[data-delete]').forEach(button => button.onclick = () => remove(button.dataset.delete));
    root().querySelectorAll('[data-clear]').forEach(button => button.onclick = () => {
      set(button.dataset.clear, '');
      const parent = get(button.dataset.clear.split('.').slice(0,-1).join('.'));
      if ('crop' in parent) parent.crop = null;
      render();
      status('图片已从当前编辑内容清除，请保存使修改生效。');
    });
    root().querySelectorAll('[data-move]').forEach(button => button.onclick = () => {
      const parts = button.dataset.move.split('.');
      const index = Number(parts.pop());
      const list = get(parts.join('.'));
      const target = index + Number(button.dataset.direction);
      if (target < 0 || target >= list.length) return;
      [list[index], list[target]] = [list[target], list[index]];
      markDirty();
      render();
    });
    root().querySelectorAll('[data-add-member]').forEach(button => button.onclick = () => {
      get(button.dataset.addMember).push(templates.member());
      markDirty();
      render();
    });
    root().querySelectorAll('[data-add-paragraph]').forEach(button => button.onclick = () => {
      state.pages[button.dataset.addParagraph].paragraphs.push(tri());
      markDirty();
      render();
    });
    root().querySelector('#add-entry')?.addEventListener('click', () => {
      state[section].push(templates[section]());
      markDirty();
      render();
      const cards = root().querySelectorAll('.editor-card');
      const last = cards[cards.length - 1];
      last.open = true;
      last.scrollIntoView({
        block: 'center'
      });
    });
    root().querySelectorAll('[data-upload]').forEach(input => input.onchange = async () => {
      if (busy || !input.files[0]) return;
      const file = input.files[0];
      if (file.size > 12 * 1024 * 1024) {
        status('图片不能超过 12 MiB（约 12.6 MB），原图片和当前修改仍保留。',true);
        input.value = '';
        return;
      }
      if (file.type && !['image/png','image/jpeg','image/gif','image/webp'].includes(file.type)) {
        status('请选择 PNG、JPEG、GIF 或 WebP 图片，原图片和当前修改仍保留。',true);
        input.value = '';
        return;
      }
      const body = new FormData();
      body.append('file', file);
      setBusy(true);
      status('正在上传图片…');
      try {
        const result = await api('/upload', {
          method: 'POST',
          body
        });
        if (!result.url || !editing.validUrl(result.url,true)) throw Error('上传响应不完整，原图片和当前修改仍保留。请稍后重试。');
        set(input.dataset.upload, result.url);
        const parent = get(input.dataset.upload.split('.').slice(0, -1).join('.'));
        if ('crop' in parent) parent.crop = null;
        if (input.dataset.upload === 'settings.opening' && result.duration) state.settings.openingDuration = result.duration;
        render();
        status('图片已上传，尚未保存。保存后按该内容的发布状态生效。');
      } catch (error) {
        status(error.message, true);
        input.value = '';
      } finally {
        setBusy(false);
      }
    });
    const saveButton = document.querySelector('#save-site');
    if (saveButton) saveButton.onclick = async event => {
      if (busy) return;
      validationErrors = editing.validateContent(state);
      if (validationErrors.length) {
        render();
        status('内容尚未保存，请检查提示中的字段。当前修改仍保留。',true);
        revealField(validationErrors[0].path);
        status('内容尚未保存，请检查提示中的字段。当前修改仍保留。',true);
        return;
      }
      setBusy(true);
      status('正在保存、翻译并发布，请稍候…');
      try {
        const merchantOnly = !can('site.write');
        const result = await api(merchantOnly ? '/admin/merchants' : '/admin/site', {
          method: 'PUT',
          body: JSON.stringify({
            revision,
            data: merchantOnly ? Object.fromEntries(['merchants', 'regions', 'categories'].map(key => [key, state[key]])) : state
          })
        });
        const required = merchantOnly ? ['merchants','regions','categories'] : Object.keys(state);
        if (result.saved !== true || !Number.isSafeInteger(result.revision) || !result.data || typeof result.data !== 'object' || Array.isArray(result.data) || required.some(key=>!(key in result.data))) {
          throw Error('保存响应不完整，当前修改仍保留。请先导出内容并核对服务器是否已经保存。');
        }
        const warnings = Array.isArray(result.warnings) ? result.warnings : [];
        revision = result.revision;
        state = merchantOnly ? {...state, ...result.data} : result.data;
        dirty = false;
        render();
        status(`已保存第 ${revision} 次更新。已发布的内容将在官网下次打开或刷新时显示。` + (warnings.length ? ' ' + warnings.join(' ') : ''), warnings.length > 0);
      } catch (error) {
        status(error.message, true);
      } finally {
        setBusy(false);
      }
    };
    document.querySelector('#logout').onclick = async () => {
      if (busy) return;
      if (dirty && !confirm('有未保存修改，仍然退出吗？')) return;
      setBusy(true);
      try {
        await api('/logout', {method:'POST'});
        dirty = false;
        location.reload();
      } catch (error) { status(error.message,true); }
      finally { setBusy(false); }
    };
    root().querySelectorAll('.account-form').forEach(form => form.onsubmit = async event => {
      event.preventDefault();
      const button = form.querySelector('[type="submit"]');
      const id = form.dataset.accountId;
      if (id !== 'new' && Number(id) === currentUser.id && dirty && !confirm('修改自己的账号会重新登录，未保存内容可能丢失。已导出内容并确认继续吗？')) return;
      const payload = {
        username: form.elements.namedItem('username').value.trim(),
        password: form.elements.namedItem('password').value,
        role: form.elements.namedItem('role').value,
        active: form.elements.namedItem('active').checked,
        permissions: [...form.querySelectorAll('[name="permissions"]:checked')].map(input => input.value)
      };
      button.disabled = true;
      try {
        await api(id === 'new' ? '/admin/accounts' : `/admin/accounts/${id}`, {
          method: id === 'new' ? 'POST' : 'PUT',
          body: JSON.stringify(payload)
        });
        if (id !== 'new' && Number(id) === currentUser.id) {
          location.reload();
          return;
        }
        accounts = (await api('/admin/accounts')).accounts;
        render();
        status(id === 'new' ? '账号已创建。' : '账号已更新。');
      } catch (error) {
        status(error.message, true);
      } finally {
        button.disabled = false;
      }
    });
  }

  function login() {
    root().innerHTML = '<form class="cms-login"><h1>管理员登录</h1><p>登录后可使用分配给你的管理功能。</p><label>账号<input name="username" value="admin" autocomplete="username" required></label><label>密码<input name="password" type="password" autocomplete="current-password" required></label><button class="button primary">登录</button><p id="cms-status" role="status"></p></form>';
    root().querySelector('form').onsubmit = async event => {
      event.preventDefault();
      const form = new FormData(event.currentTarget);
      try {
        const result = await api('/login', {
          method: 'POST',
          body: JSON.stringify(Object.fromEntries(form))
        });
        csrf = result.csrf;
        currentUser = result.user;
        await load();
      } catch (error) {
        status(error.message, true);
      }
    };
  }
  async function load() {
    if (can('site.read') || can('merchant.read')) {
      const result = await api(can('site.read') ? '/admin/site' : '/admin/merchants');
      state = result.data;
      revision = result.revision;
    }
    if (isSuper()) accounts = (await api('/admin/accounts')).accounts;
    render();
    if (can('site.read')) {
      const translation = await api('/translation-status');
      if (!translation.configured) status('英文翻译服务尚未配置。简繁中文可直接保存；已有英文正常显示。');
    }
  }
  window.addEventListener('beforeunload', event => {
    if (dirty) {
      event.preventDefault();
      event.returnValue = '';
    }
  });
  api('/session').then(result => {
    csrf = result.csrf;
    currentUser = result.user;
    return result.authenticated ? load() : login();
  }).catch(error => {
    login();
    status(error.message, true);
  });
})();
